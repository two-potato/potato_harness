"""Host-managed seller group is required for catalog writes (no self-elevation)."""
from rest_framework import permissions


class SellerWritePermission(permissions.BasePermission):
    """Anonymous visitors may browse; only authenticated seller role can mutate."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        return bool(user and user.is_authenticated and user.groups.filter(name="seller").exists())
