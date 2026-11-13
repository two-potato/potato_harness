"""Host-managed Django roles: users cannot grant themselves seller/moderator rights."""
from rest_framework import permissions


def has_group(user, group):
    return bool(user and user.is_authenticated and user.is_active
                and user.groups.filter(name=group).exists())


class IsSeller(permissions.BasePermission):
    def has_permission(self, request, view):
        return has_group(request.user, "seller")


class SellerWritePermission(permissions.BasePermission):
    """Anonymous visitors may browse; only active sellers may mutate."""
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS or has_group(request.user, "seller")


class IsModerator(permissions.BasePermission):
    """Local MVP review requires both trusted staff status and moderator role."""
    def has_permission(self, request, view):
        user = request.user
        return bool(has_group(user, "moderator") and user.is_staff)
