from rest_framework import serializers
from .models import Listing


class ListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Listing
        fields = ["id", "slug", "title", "description", "price", "currency", "status",
                  "content_revision", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "content_revision", "created_at", "updated_at"]

    def validate_currency(self, currency):
        # R2 KZ fixture only; full country pack resolver is not available.
        if currency != "KZT":
            raise serializers.ValidationError("Only KZT sandbox fixture is supported")
        return currency


class RevisionSerializer(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=1)
