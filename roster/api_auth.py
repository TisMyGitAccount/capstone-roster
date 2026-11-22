from django.contrib.auth.models import AnonymousUser
from rest_framework import authentication, exceptions, permissions

from .models import ApiToken


class ApiTokenAuthentication(authentication.BaseAuthentication):
    """Reads 'Authorization: Bearer <token>' and checks it against stored hashes."""

    keyword = "Bearer"

    def authenticate(self, request):
        parts = authentication.get_authorization_header(request).split()
        if not parts or parts[0].lower() != b"bearer":
            return None  # not a token request; let other authenticators try
        if len(parts) != 2:
            raise exceptions.AuthenticationFailed("Malformed Authorization header.")
        try:
            raw = parts[1].decode("ascii")
        except UnicodeError:
            raise exceptions.AuthenticationFailed("Malformed token.")
        token = ApiToken.from_raw_key(raw)
        if token is None:
            raise exceptions.AuthenticationFailed("Invalid or revoked token.")
        return (AnonymousUser(), token)

    def authenticate_header(self, request):
        return self.keyword


class IsRosterReader(permissions.BasePermission):
    """Allow a valid API token, or a logged-in admin (handy for browser testing)."""

    message = "Authentication required: send 'Authorization: Bearer <token>'."

    def has_permission(self, request, view):
        if isinstance(request.auth, ApiToken):
            return True
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)