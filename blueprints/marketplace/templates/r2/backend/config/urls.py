from django.urls import include, path
from django.http import JsonResponse


def health(_request):
    # Process reachability only, not a proof of dependency readiness.
    return JsonResponse({"status": "process_up", "ready": False})

urlpatterns = [
    path("health/", health),
    path("api/", include("catalog.urls")),
]
