from rest_framework import serializers
from .models import Listing


class ListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Listing
        fields = ["id", "slug", "title", "description", "price", "currency", "status",
                  "content_revision", "approved_revision", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "content_revision", "approved_revision",
                            "created_at", "updated_at"]

    def validate_currency(self, currency):
        if currency != "KZT":
            raise serializers.ValidationError("Only KZT sandbox fixture is supported")
        return currency


class RevisionSerializer(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=1)


class DecisionSerializer(RevisionSerializer):
    decision_id = serializers.UUIDField()
    verdict = serializers.ChoiceField(choices=("APPROVE", "REJECT"))
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")
