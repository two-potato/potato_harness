"""Local MVP API: seller revision workflow and human moderator decisions."""
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Listing, ModerationDecision
from .moderation import content_digest
from .permissions import IsModerator, IsSeller, SellerWritePermission
from .serializers import DecisionSerializer, ListingSerializer, RevisionSerializer


class ListingListCreate(generics.ListCreateAPIView):
    serializer_class = ListingSerializer
    permission_classes = [SellerWritePermission]

    def get_queryset(self):
        visible = Q(status=Listing.Status.PUBLISHED, approved_revision=F("content_revision"))
        user = self.request.user
        if user and user.is_authenticated and user.is_active:
            visible |= Q(seller=user)
        return Listing.objects.filter(visible).order_by("id")

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user, status=Listing.Status.DRAFT,
                        approved_revision=None)


class ListingMine(generics.ListAPIView):
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticated, IsSeller]

    def get_queryset(self):
        return Listing.objects.filter(seller=self.request.user).order_by("-created_at", "id")


class ListingDetail(generics.RetrieveUpdateAPIView):
    serializer_class = ListingSerializer
    permission_classes = [SellerWritePermission]

    def get_queryset(self):
        user = self.request.user
        if self.request.method not in permissions.SAFE_METHODS:
            return Listing.objects.filter(seller=user) if user and user.is_authenticated and user.is_active else Listing.objects.none()
        visible = Q(status=Listing.Status.PUBLISHED, approved_revision=F("content_revision"))
        if user and user.is_authenticated and user.is_active:
            visible |= Q(seller=user)
        return Listing.objects.filter(visible)

    def update(self, request, *args, **kwargs):
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
    permission_classes = [permissions.IsAuthenticated, IsSeller]

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


class ModerationQueue(generics.ListAPIView):
    """Only trusted local staff may see submissions awaiting human review."""
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticated, IsModerator]
    def get_queryset(self):
        return Listing.objects.filter(status=Listing.Status.PENDING_REVIEW).order_by("created_at", "id")


class ModerationDecide(APIView):
    permission_classes = [permissions.IsAuthenticated, IsModerator]

    def post(self, request, pk):
        submitted = DecisionSerializer(data=request.data)
        submitted.is_valid(raise_exception=True)
        payload = submitted.validated_data
        revision, decision_id = payload["expected_revision"], payload["decision_id"]
        verdict, reason = payload["verdict"], payload["reason"]
        with transaction.atomic():
            listing = get_object_or_404(Listing.objects.select_for_update(), pk=pk)
            prior = ModerationDecision.objects.filter(pk=decision_id).first()
            if prior is not None:
                if (prior.listing_id != listing.pk or prior.content_revision != revision or
                        prior.verdict != verdict or prior.reason != reason or prior.moderator_id != request.user.pk):
                    return Response({"error": "decision_identity_conflict"}, status=409)
                return Response(_receipt(prior), status=200)
            if listing.content_revision != revision or listing.status != Listing.Status.PENDING_REVIEW:
                return Response({"error": "stale_or_unsubmitted_revision"}, status=409)
            if ModerationDecision.objects.filter(listing=listing, content_revision=revision).exists():
                return Response({"error": "revision_already_reviewed"}, status=409)
            decision = ModerationDecision.objects.create(
                id=decision_id, listing=listing, moderator=request.user,
                content_revision=revision, content_sha256=content_digest(listing),
                verdict=verdict, reason=reason,
            )
            listing.status = Listing.Status.PUBLISHED if verdict == "APPROVE" else Listing.Status.REJECTED
            listing.approved_revision = revision if verdict == "APPROVE" else None
            listing.save(update_fields=["status", "approved_revision", "updated_at"])
        return Response(_receipt(decision), status=200)


def _receipt(decision):
    return {"decision_id": str(decision.pk), "listing_id": str(decision.listing_id),
            "content_revision": decision.content_revision, "content_sha256": decision.content_sha256,
            "verdict": decision.verdict, "resulting_status": (Listing.Status.PUBLISHED if decision.verdict == "APPROVE"
                                                  else Listing.Status.REJECTED)}
