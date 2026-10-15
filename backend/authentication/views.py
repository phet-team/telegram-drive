import time
import hmac
import hashlib
import logging
from rest_framework import status, views, permissions

logger = logging.getLogger(__name__)
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from django.contrib.auth import get_user_model
from django.core.cache import cache
from config.env_schema import config
from authentication.serializers import (
    RegisterSerializer, LoginSerializer, UserSerializer,
    TelegramAuthSerializer, GoogleAuthSerializer
)
from authentication.throttles import StrictLoginRateThrottle

User = get_user_model()


REFRESH_COOKIE_NAME = 'refresh_token'
REFRESH_COOKIE_PATH = '/api/auth/'


def set_refresh_cookie(response, refresh_token_str):
    """Stores the long-lived refresh token in an HttpOnly, SameSite=Lax, Secure cookie."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token_str,
        max_age=config.JWT_REFRESH_TTL_DAYS * 86400,
        httponly=True,
        samesite='Lax',
        secure=not config.DEBUG,
        path=REFRESH_COOKIE_PATH
    )


def clear_refresh_cookie(response):
    """Destroys the refresh token cookie upon logout or token invalidation."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        samesite='Lax'
    )


def build_auth_response(user, tokens, status_code=status.HTTP_200_OK, message=None):
    """Constructs hardened auth response: access token in JSON body, refresh token in HttpOnly cookie."""
    data = {
        'user': UserSerializer(user).data,
        'access': tokens['access'],
        'tokens': {
            'access': tokens['access'],
        }
    }
    if message:
        data['message'] = message
    response = Response(data, status=status_code)
    set_refresh_cookie(response, tokens['refresh'])
    return response


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }


class RegisterView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [StrictLoginRateThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        tokens = get_tokens_for_user(user)
        return build_auth_response(
            user, tokens, status_code=status.HTTP_201_CREATED, message='Registration successful'
        )


class LoginView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [StrictLoginRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        tokens = get_tokens_for_user(user)
        return build_auth_response(user, tokens, status_code=status.HTTP_200_OK)


class CookieTokenRefreshView(views.APIView):
    """
    Hardened Token Refresh View:
    1. Reads refresh_token from HttpOnly cookie (or JSON body for testing/programmatic clients).
    2. Enforces rotation: blacklists the used refresh token and issues a new refresh token.
    3. Attaches newly issued refresh token in HttpOnly cookie.
    4. Returns new short-lived access token in JSON body for in-memory client state.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME) or request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'Refresh token not provided'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh_token)
            user_id = token.payload.get('user_id')
            user = User.objects.filter(id=user_id).first()
            if not user or not user.is_active:
                return Response({'error': 'User not found or inactive'}, status=status.HTTP_401_UNAUTHORIZED)

            # Token rotation: Blacklist old token
            token.blacklist()

            # Issue new token pair
            new_tokens = get_tokens_for_user(user)

            response = Response({
                'access': new_tokens['access'],
                'tokens': {
                    'access': new_tokens['access'],
                },
                'user': UserSerializer(user).data,
            }, status=status.HTTP_200_OK)

            set_refresh_cookie(response, new_tokens['refresh'])
            return response
        except Exception as e:
            logger.warning(f"Token refresh rejected: {e}")
            response = Response({'error': 'Invalid, expired or revoked refresh token'}, status=status.HTTP_401_UNAUTHORIZED)
            clear_refresh_cookie(response)
            return response


class MeView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class LogoutView(views.APIView):
    """
    Hardened Logout View:
    Invalidates refresh token on server (Blacklist) and destroys HttpOnly cookie.
    Permits unauthenticated requests so expired access token doesn't block logout.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME) or request.data.get('refresh')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception as e:
                logger.warning(f"Logout token blacklist notice: {e}")

        response = Response({'message': 'Logged out successfully'}, status=status.HTTP_200_OK)
        clear_refresh_cookie(response)
        return response


class TelegramAuthView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [StrictLoginRateThrottle]

    def post(self, request):
        serializer = TelegramAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Dev Mock bypass for local testing on localhost
        if config.DEBUG and data.get('is_dev_mock'):
            tg_id = data.get('id') or 8597896963
            name = data.get('first_name') or 'Dev Telegram User'
            username = data.get('username') or 'dev_tg_user'
            avatar_url = data.get('photo_url') or ''
            user = User.objects.filter(telegram_id=tg_id).first()
            if not user:
                email = f"tg_{tg_id}@telegram.user"
                user = User.objects.filter(email=email).first()
                if user:
                    user.telegram_id = tg_id
                    user.save(update_fields=['telegram_id'])
                else:
                    user = User.objects.create_user(
                        email=email,
                        name=name,
                        telegram_id=tg_id,
                        avatar_url=avatar_url,
                        storage_quota=None
                    )
            tokens = get_tokens_for_user(user)
            return build_auth_response(user, tokens, status_code=status.HTTP_200_OK)

        bot_token = config.TELEGRAM_BOT_TOKEN.strip() if config.TELEGRAM_BOT_TOKEN else ''
        if not bot_token:
            return Response({'error': 'Telegram OAuth is not configured on server'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # 1. Anti-Replay: Verify auth_date within 24 hours
        auth_date = data['auth_date']
        if abs(time.time() - auth_date) > 86400:
            return Response({'error': 'Telegram authentication data has expired'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Cryptographic signature check (HMAC-SHA256) strictly following Telegram Login Widget specification
        check_hash = data['hash']
        allowed_tg_fields = ['auth_date', 'first_name', 'id', 'last_name', 'photo_url', 'username']
        check_items = []
        for k in sorted(allowed_tg_fields):
            val = request.data.get(k)
            if val is not None and str(val).strip() != '':
                check_items.append(f"{k}={val}")
        data_check_string = "\n".join(check_items)

        secret_key = hashlib.sha256(bot_token.encode('utf-8')).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(computed_hash, check_hash):
            return Response({'error': 'Telegram signature verification failed'}, status=status.HTTP_401_UNAUTHORIZED)

        # Anti-Replay Cache: Prevent re-use of valid signature within 24hr window
        cache_key = f"tg_hash_{check_hash}"
        if cache.get(cache_key):
            return Response({'error': 'Telegram authentication data has already been used'}, status=status.HTTP_400_BAD_REQUEST)
        cache.set(cache_key, True, timeout=86400)

        # 3. Find or create user
        tg_id = data['id']
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        username = data.get('username', '')
        name = f"{first_name} {last_name}".strip() or username or f"Telegram User {tg_id}"
        avatar_url = data.get('photo_url', '')

        user = User.objects.filter(telegram_id=tg_id).first()
        if not user:
            email = f"tg_{tg_id}@telegram.user"
            user = User.objects.filter(email=email).first()
            if user:
                user.telegram_id = tg_id
                user.name = user.name or name
                if avatar_url and not user.avatar_url:
                    user.avatar_url = avatar_url
                user.save()
            else:
                user = User.objects.create_user(
                    email=email,
                    name=name,
                    telegram_id=tg_id,
                    avatar_url=avatar_url,
                    storage_quota=None
                )
        else:
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
                user.save(update_fields=['avatar_url'])

        tokens = get_tokens_for_user(user)
        return build_auth_response(user, tokens, status_code=status.HTTP_200_OK)


class GoogleAuthView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [StrictLoginRateThrottle]

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        id_token_str = serializer.validated_data['id_token']

        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        bot_token = config.TELEGRAM_BOT_TOKEN
        client_id = config.GOOGLE_CLIENT_ID.strip() if config.GOOGLE_CLIENT_ID else ''
        if not client_id:
            return Response({'error': 'Google OAuth is not configured on server'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            id_info = id_token.verify_oauth2_token(
                id_token_str, google_requests.Request(), audience=client_id
            )
            
            google_sub = id_info['sub']
            email = id_info.get('email', '').lower()
            name = id_info.get('name', '')
            picture = id_info.get('picture', '')

            user = User.objects.filter(google_sub=google_sub).first()
            if not user:
                existing_user = User.objects.filter(email=email).first()
                if existing_user:
                    existing_user.google_sub = google_sub
                    if picture and not existing_user.avatar_url:
                        existing_user.avatar_url = picture
                    existing_user.save()
                    user = existing_user
                else:
                    user = User.objects.create_user(
                        email=email,
                        name=name,
                        google_sub=google_sub,
                        avatar_url=picture,
                        storage_quota=None
                    )

            tokens = get_tokens_for_user(user)
            return build_auth_response(user, tokens, status_code=status.HTTP_200_OK)

        except Exception as e:
            logger.warning(f"Google token verification failed: {e}")
            return Response({'error': 'Google token verification failed'}, status=status.HTTP_400_BAD_REQUEST)
