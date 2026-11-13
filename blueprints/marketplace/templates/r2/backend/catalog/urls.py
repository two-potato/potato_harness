"""Canonical Django API routes plus exact no-slash aliases for Next.js rewrites.

Next.js external rewrites can normalize away a terminal slash. Redirecting a
session/CSRF POST from /api/... to /api/.../ is unsafe and breaks local login.
Both spellings invoke the SAME decorated view and identical permissions.
"""
from django.urls import path
from .auth_views import session, sign_in, sign_out
from .views import (ListingDetail, ListingListCreate, ListingMine, ListingSubmit,
                    ModerationDecide, ModerationQueue)


routes = [
    ("auth/session/", session, "auth-session"),
    ("auth/login/", sign_in, "auth-login"),
    ("auth/logout/", sign_out, "auth-logout"),
    ("listings/", ListingListCreate.as_view(), "listings"),
    ("listings/<uuid:pk>/", ListingDetail.as_view(), "listing-detail"),
    ("listings/<uuid:pk>/submit/", ListingSubmit.as_view(), "listing-submit"),
    ("me/listings/", ListingMine.as_view(), "my-listings"),
    ("moderation/queue/", ModerationQueue.as_view(), "moderation-queue"),
    ("moderation/<uuid:pk>/decision/", ModerationDecide.as_view(), "moderation-decision"),
]

urlpatterns = []
for route, view, name in routes:
    urlpatterns.append(path(route, view, name=name))
    urlpatterns.append(path(route.removesuffix("/"), view))
