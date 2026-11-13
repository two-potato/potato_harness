from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(_request):
    # Process reachability, not a proof of dependency readiness.
    return JsonResponse({"status": "process_up", "ready": False})


urlpatterns = [path("health/", health), path("api/", include("catalog.urls"))]
# The Django admin is only exposed in explicit local development mode.
# Never use DEBUG=1 on a network-exposed host.
if settings.DEBUG:
    urlpatterns.append(path("admin/", admin.site.urls))
