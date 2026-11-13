from django.urls import path
from .views import ListingDetail, ListingListCreate, ListingSubmit

urlpatterns = [
    path("listings/", ListingListCreate.as_view(), name="listings"),
    path("listings/<uuid:pk>/", ListingDetail.as_view(), name="listing-detail"),
    path("listings/<uuid:pk>/submit/", ListingSubmit.as_view(), name="listing-submit"),
]
