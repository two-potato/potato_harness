"""CSRF-protected session endpoints. No public signup or self-assigned roles."""
import json
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .permissions import has_group


@ensure_csrf_cookie
@require_GET
def session(request):
    user = request.user
    authenticated = bool(user.is_authenticated and user.is_active)
    return JsonResponse({
        "authenticated": authenticated,
        "username": user.get_username() if authenticated else "",
        "seller": has_group(user, "seller") if authenticated else False,
        "moderator": bool(user.is_staff and has_group(user, "moderator")) if authenticated else False,
    })


def _json_body(request):
    if request.content_type != "application/json" or len(request.body) > 4096:
        return None
    try:
        data = json.loads(request.body)
    except (UnicodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@csrf_protect
@require_POST
def sign_in(request):
    data = _json_body(request)
    if not data or set(data) != {"username", "password"}:
        return JsonResponse({"error": "invalid_request"}, status=400)
    username, password = data["username"], data["password"]
    if not isinstance(username, str) or len(username) > 150 or not isinstance(password, str) or len(password) > 256:
        return JsonResponse({"error": "invalid_request"}, status=400)
    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        # Same generic response for invalid username/password. Add trusted-host
        # rate limiting before exposing this development endpoint publicly.
        return JsonResponse({"error": "invalid_credentials"}, status=401)
    login(request, user)
    return JsonResponse({"authenticated": True, "username": user.get_username()})


@csrf_protect
@require_POST
def sign_out(request):
    logout(request)
    return JsonResponse({"authenticated": False})
