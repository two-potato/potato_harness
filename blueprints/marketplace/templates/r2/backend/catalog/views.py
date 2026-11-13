"""Prototype endpoints: no direct seller publication, no service bypass."""
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Listing
from .serializers import ListingSerializer, RevisionSerializer
from .permissions import SellerWritePermission


class ListingListCreate(generics.ListCreateAPIView):
    serializer_class = ListingSerializer
    permission_classes = [SellerWritePermission]

    def get_queryset(self):
        # Only published-and-approved listings are public; authenticated sellers
        # see their own drafts. No unrelated seller draft exposure.
        visible = Q(status=Listing.Status.PUBLISHED, approved_revision=F("content_revision"))
        user = self.request.user
        if user and user.is_authenticated:
            visible |= Q(seller=user)
        return Listing.objects.filter(visible).order_by("id")

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user, status=Listing.Status.DRAFT,
                        approved_revision=None)


class ListingDetail(generics.RetrieveUpdateAPIView):
    serializer_class = ListingSerializer
    permission_classes = [SellerWritePermission]

    def get_queryset(self):
        user = self.request.user
        if self.request.method not in permissions.SAFE_METHODS:
            return Listing.objects.filter(seller=user) if user and user.is_authenticated else Listing.objects.none()
        visible = Q(status=Listing.Status.PUBLISHED, approved_revision=F("content_revision"))
        if user and user.is_authenticated:
            visible |= Q(seller=user)
        return Listing.objects.filter(visible)

    def update(self, request, *args, **kwargs):
        # Updates are revision-bound to prevent lost edits and unreviewed publish.
        revision = RevisionSerializer(data=request.data)
        revision.is_valid(raise_exception=True)
        with transaction.atomic():
            instance = get_object_or_404(self.get_queryset().select_for_update(), pk=kwargs["pk"])
            if instance.content_revision != revision.validated_data["expected_revision"]:
                raise ValidationError({"expected_revision": "stale_revision"})
            data = {k: v for k, v in request.data.items() if k != "expected_revision"}
            serializer = self.get_serializer(instance, data=data, partial=kwargs.get("partial", False))
            serializer.is_valid(raise_exception=True)
            serializer.save(content_revision=instance.content_revision + 1,
                            status=Listing.Status.DRAFT, approved_revision=None)
            return Response(serializer.data)


class ListingSubmit(APIView):
    permission_classes = [permissions.IsAuthenticated, SellerWritePermission]

    def post(self, request, pk):
        rev = RevisionSerializer(data=request.data)
        rev.is_valid(raise_exception=True)
        with transaction.atomic():
            listing = get_object_or_404(Listing.objects.select_for_update(), pk=pk, seller=request.user)
            if listing.content_revision != rev.validated_data["expected_revision"]:
                raise ValidationError({"expected_revision": "stale_revision"})
            if listing.status != Listing.Status.DRAFT:
                raise ValidationError({"status": "draft_required"})
            listing.status = Listing.Status.PENDING_REVIEW
            listing.save(update_fields=["status", "updated_at"])
        return Response({"status": Listing.Status.PENDING_REVIEW,
                         "content_revision": listing.content_revision}, status=status.HTTP_200_OK)
