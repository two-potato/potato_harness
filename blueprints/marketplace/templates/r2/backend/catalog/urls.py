from django.urls import path
from .auth_views import session, sign_in, sign_out
from .views import (ListingDetail, ListingListCreate, ListingMine, ListingSubmit,
                    ModerationDecide, ModerationQueue)

urlpatterns = [
    path("auth/session/", session, name="auth-session"),
    path("auth/login/", sign_in, name="auth-login"),
    path("auth/logout/", sign_out, name="auth-logout"),
    path("listings/", ListingListCreate.as_view(), name="listings"),
    path("listings/<uuid:pk>/", ListingDetail.as_view(), name="listing-detail"),
    path("listings/<uuid:pk>/submit/", ListingSubmit.as_view(), name="listing-submit"),
    path("me/listings/", ListingMine.as_view(), name="my-listings"),
    path("moderation/queue/", ModerationQueue.as_view(), name="moderation-queue"),
    path("moderation/<uuid:pk>/decision/", ModerationDecide.as_view(), name="moderation-decision"),
]
