from datetime import timedelta

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from authentication.models import ApiToken
from authentication.throttles import get_client_ip

LAST_USED_MIN_INTERVAL = timedelta(seconds=60)


class ApiTokenAuthentication(BaseAuthentication):
    """
    Authenticates requests carrying `Authorization: Bearer tdk_...`.

    - No header, or a Bearer token without the `tdk_` prefix: return None so
      JWTAuthentication handles it exactly as before.
    - Unknown hash, revoked token, or inactive user: AuthenticationFailed with
      a specific message.
    - On success returns (token.user, token) so `request.auth` is the ApiToken.
    """
    keyword = 'Bearer'

    def authenticate(self, request):
        auth = request.headers.get('Authorization')
        if not auth:
            return None

        scheme, _, credentials = auth.partition(' ')
        if scheme.lower() != self.keyword.lower():
            return None
        credentials = credentials.strip()
        if not credentials:
            return None
        if not credentials.startswith('tdk_'):
            # Not an API token — let the JWT backend pick it up.
            return None

        token_hash = ApiToken.hash_token(credentials)
        token = ApiToken.objects.select_related('user').filter(token_hash=token_hash).first()
        if token is None:
            raise AuthenticationFailed('invalid API token')

        if token.revoked_at is not None:
            raise AuthenticationFailed('API token revoked')

        if not token.user.is_active:
            raise AuthenticationFailed('user inactive')

        self._maybe_touch_last_used(token, request)
        return (token.user, token)

    def authenticate_header(self, request):
        # Ensures AuthenticationFailed surfaces as 401 (not downgraded to 403)
        return 'Bearer realm="api-token"'

    def _maybe_touch_last_used(self, token, request):
        """Updates last_used_at / last_used_ip at most once per 60 s per token."""
        now = timezone.now()
        if token.last_used_at is not None and (now - token.last_used_at) < LAST_USED_MIN_INTERVAL:
            return
        client_ip = get_client_ip(request)
        # race-safe: only touch if never used or still older than the interval at write time
        from django.db.models import Q
        updated = ApiToken.objects.filter(
            pk=token.pk,
        ).filter(
            Q(last_used_at__isnull=True) | Q(last_used_at__lt=now - LAST_USED_MIN_INTERVAL),
        ).update(last_used_at=now, last_used_ip=client_ip[:45])
        if updated:
            token.last_used_at = now
            token.last_used_ip = client_ip[:45]
