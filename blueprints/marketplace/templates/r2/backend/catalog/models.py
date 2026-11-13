"""Catalog authority: seller-owned listings with revision-bound publication state."""
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class Listing(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_REVIEW = "PENDING_REVIEW", "Pending review"
        PUBLISHED = "PUBLISHED", "Published"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="listings")
    slug = models.SlugField(max_length=80)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, max_length=4096)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="KZT")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    content_revision = models.PositiveIntegerField(default=1)
    approved_revision = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["seller", "slug"], name="listing_seller_slug_unique"),
            models.CheckConstraint(condition=Q(price__gte=0), name="listing_price_nonnegative"),
        ]

    @property
    def is_visible(self):
        return self.status == self.Status.PUBLISHED and self.approved_revision == self.content_revision


class ModerationDecision(models.Model):
    """Immutable decision receipt. One successful decision per content revision."""
    class Verdict(models.TextChoices):
        APPROVE = "APPROVE", "Approve"
        REJECT = "REJECT", "Reject"

    id = models.UUIDField(primary_key=True, editable=False)
    listing = models.ForeignKey(Listing, on_delete=models.PROTECT, related_name="moderation_decisions")
    moderator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    content_revision = models.PositiveIntegerField()
    content_sha256 = models.CharField(max_length=71)
    verdict = models.CharField(max_length=7, choices=Verdict.choices)
    reason = models.CharField(max_length=300, blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["listing", "content_revision"], name="one_moderation_verdict_per_revision"),
        ]
