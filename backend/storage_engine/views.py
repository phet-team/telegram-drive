import logging
import re
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status, views
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from authentication.token_permissions import ApiTokenScopePermission, get_api_token
from drive.models import FileItem, StorageSettings, UserStorageAccount
from storage_engine import accounts, alerts, credentials, health, login
from storage_engine.errors import StorageEngineError
from storage_engine.secrets import decrypt, CredentialsUnreadable
from storage_engine.selftest import run_selftest

User = get_user_model()

logger = logging.getLogger(__name__)

CHAT_ID_RE = re.compile(r'^(-?\d+|@[A-Za-z0-9_]{3,64})$')
PHONE_RE = re.compile(r'^\+\d{6,15}$')


class StorageHealthView(views.APIView):
    """Public, cheap health probe. Never returns secrets or the chat id."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        ok, reason = health.check_health()
        if ok:
            return Response({'ok': True})
        response = Response({'ok': False, 'reason': reason}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        response['Retry-After'] = '30'
        return response


class IsStorageAdmin(permissions.BasePermission):
    """Superusers authenticated with a normal login. API tokens never qualify."""
    message = "Only superusers can manage storage."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser and get_api_token(request) is None)


class StorageAdminView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, ApiTokenScopePermission, IsStorageAdmin]


def _credentials_unreadable(row) -> bool:
    if not row.has_session:
        return False
    try:
        decrypt(row.session_string_enc)
    except CredentialsUnreadable:
        return True
    return False


def serialize_settings(row):
    """Never includes secrets: no session, no codes; the webhook URL is reduced to its host (Discord/Slack URLs carry a token)."""
    snap = credentials.get_snapshot(force=True)
    return {
        'auth_mode': row.auth_mode,
        'chat_id': row.chat_id,
        'has_session': row.has_session,
        'credentials_unreadable': _credentials_unreadable(row),
        'effective_source': snap.source,
        'alert_format': row.alert_format,
        'alert_webhook_set': bool(row.alert_webhook_url),
        'alert_webhook_host': urlparse(row.alert_webhook_url).hostname or '',
        'alert_telegram_chat_id': row.alert_telegram_chat_id,
        'alert_min_interval_minutes': row.alert_min_interval_minutes,
        'status': {
            'alert_state': row.alert_state,
            'last_alert_at': row.last_alert_at,
            'last_check_at': row.last_check_at,
            'last_check_ok': row.last_check_ok,
            'last_check_reason': row.last_check_reason,
        },
        'login_pending': row.login_seconds_left() > 0,
        'login_seconds_left': row.login_seconds_left(),
        'updated_at': row.updated_at,
    }


class StorageSettingsUpdateSerializer(serializers.Serializer):
    chat_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    alert_format = serializers.ChoiceField(choices=[c[0] for c in StorageSettings.FORMAT_CHOICES], required=False)
    alert_webhook_url = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    alert_telegram_chat_id = serializers.CharField(required=False, allow_blank=True, max_length=32)
    alert_min_interval_minutes = serializers.IntegerField(required=False, min_value=5, max_value=1440)
    session_string = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=4096, trim_whitespace=True)

    def validate_chat_id(self, value):
        value = value.strip()
        if value and not CHAT_ID_RE.match(value):
            raise serializers.ValidationError("Use a numeric chat id (e.g. -100123...) or @username, or leave blank for Saved Messages.")
        return value

    def validate_alert_webhook_url(self, value):
        value = value.strip()
        if value:
            try:
                alerts.validate_webhook_url(value)
            except ValueError as exc:
                raise serializers.ValidationError(str(exc))
        return value

    def validate_alert_telegram_chat_id(self, value):
        value = value.strip()
        if value and not value.isdigit():
            raise serializers.ValidationError("Use the numeric Telegram user id.")
        return value

    def validate_session_string(self, value):
        if not value:
            return value
        from telethon.sessions import StringSession
        try:
            StringSession(value)
        except Exception:
            raise serializers.ValidationError("This is not a valid Telethon session string.")
        return value


class StorageSettingsView(StorageAdminView):
    def get(self, request):
        return Response(serialize_settings(StorageSettings.get_solo()))

    def put(self, request):
        serializer = StorageSettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = StorageSettings.get_solo()

        changed = []
        for field in ('chat_id', 'alert_format', 'alert_webhook_url', 'alert_telegram_chat_id', 'alert_min_interval_minutes'):
            if field in data and getattr(row, field) != data[field]:
                setattr(row, field, data[field])
                changed.append(field)

        session_changed = False
        if 'session_string' in data:
            value = data['session_string']
            if value is None:
                row.session_string_enc = ''
                session_changed = True
            elif value:
                from storage_engine.secrets import encrypt
                row.session_string_enc = encrypt(value)
                row.auth_mode = StorageSettings.AUTH_SESSION
                row.clear_pending_login()
                session_changed = True
        if session_changed:
            changed += ['session_string_enc', 'auth_mode'] + StorageSettings.PENDING_FIELDS

        if changed:
            row.updated_by = request.user
            row.save(update_fields=sorted(set(changed + ['updated_by', 'updated_at'])))
            credentials.invalidate()
            if session_changed:
                health.reset()
            logger.info("Storage settings updated by user id=%s fields=%s", request.user.id, sorted(set(changed)))
        return Response(serialize_settings(row))


class StorageTestView(StorageAdminView):
    def post(self, request):
        ok, reason = health.check_health(force=True)
        return Response({'ok': ok, 'reason': reason})


class StorageTestAlertView(StorageAdminView):
    def post(self, request):
        row = StorageSettings.get_solo()
        if not row.alert_webhook_url and not row.alert_telegram_chat_id:
            return Response(
                {'error': 'Set a webhook URL or a Telegram user id first.'}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response({'results': alerts.send_test(row)})


class SelftestSerializer(serializers.Serializer):
    size_mb = serializers.IntegerField(min_value=1, max_value=16, default=8)


class StorageSelftestView(StorageAdminView):
    def post(self, request):
        serializer = SelftestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(run_selftest(serializer.validated_data['size_mb']))


# -- Reconnect wizard ---------------------------------------------------------------------------

class LoginStartThrottle(UserRateThrottle):
    scope = 'storage_login'


class LoginStartSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)

    def validate_phone(self, value):
        cleaned = re.sub(r'[\s\-()]', '', value)
        if not PHONE_RE.match(cleaned):
            raise serializers.ValidationError("Use the international format, e.g. +66812345678.")
        return cleaned


class LoginCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=16, trim_whitespace=True)


class LoginPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=256, trim_whitespace=False)


def _login_error(exc):
    response = Response({'ok': False, 'error': exc.message}, status=exc.status)
    if exc.retry_after:
        response['Retry-After'] = str(exc.retry_after)
    return response


class StorageLoginStartView(StorageAdminView):
    throttle_classes = [LoginStartThrottle]

    def post(self, request):
        serializer = LoginStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            expires_in = login.start(request.user, serializer.validated_data['phone'])
        except login.LoginError as exc:
            return _login_error(exc)
        return Response({'ok': True, 'expires_in': expires_in})


class StorageLoginVerifyView(StorageAdminView):
    def post(self, request):
        serializer = LoginCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(login.verify_code(request.user, serializer.validated_data['code']))
        except login.LoginError as exc:
            return _login_error(exc)


class StorageLoginPasswordView(StorageAdminView):
    def post(self, request):
        serializer = LoginPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(login.verify_password(request.user, serializer.validated_data['password']))
        except login.LoginError as exc:
            return _login_error(exc)


class StorageLoginCancelView(StorageAdminView):
    def post(self, request):
        login.cancel()
        return Response({'ok': True})
# -- Per-user storage ("My storage") ---------------------------------------------------------------------

class IsNormalUser(permissions.BasePermission):
    """Authenticated with a normal login. API tokens never qualify."""
    message = "Only normal logins can manage personal storage."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and get_api_token(request) is None)


class UserStorageView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsNormalUser]


def serialize_user_storage_me(user):
    """Full view of the caller's storage state. Never includes secrets."""
    account = getattr(user, 'storage_account', None)
    own_connected = bool(account and account.has_session)
    file_qs = account.files.all() if account else FileItem.objects.none()
    file_count = file_qs.count()
    bytes_used = file_qs.aggregate(total=Sum('size'))['total'] or 0

    try:
        target = accounts.resolve_upload_target(user)
        effective_target = 'own' if target else 'system'
        can_upload = True
    except accounts.StorageNotConnected:
        effective_target = None
        can_upload = False

    return {
        'system_allowed': user.can_use_system_storage,
        'upload_target': user.upload_target,
        'effective_target': effective_target,
        'can_upload': can_upload,
        'own': {
            'connected': own_connected,
            'status': account.status if account else 'disconnected',
            'reason': account.last_check_reason if account else '',
            'account_name': account.tg_display_name if account else '',
            'connected_at': account.connected_at if account else None,
            'file_count': file_count,
            'bytes': bytes_used,
        },
        'login_pending': account.login_seconds_left() > 0 if account else False,
        'login_seconds_left': account.login_seconds_left() if account else 0,
        'system_quota': {
            'used': user.storage_used,
            'reserved': user.storage_reserved,
            'quota': user.storage_quota,
        },
    }


class UserStorageMeView(UserStorageView):
    def get(self, request):
        return Response(serialize_user_storage_me(request.user))

    def put(self, request):
        target = request.data.get('upload_target')
        if target not in ('own', 'system'):
            raise serializers.ValidationError({"upload_target": "Invalid upload_target"})
        if target == 'system' and not request.user.can_use_system_storage:
            return Response({'error': 'System storage is not allowed for your account.'},
                            status=status.HTTP_400_BAD_REQUEST)
        account = getattr(request.user, 'storage_account', None)
        if target == 'own' and (not account or not account.has_session):
            return Response({'error': 'Connect your Telegram account first.'},
                            status=status.HTTP_400_BAD_REQUEST)
        request.user.upload_target = target
        request.user.save(update_fields=['upload_target'])
        return Response(serialize_user_storage_me(request.user))


def _my_account(request) -> UserStorageAccount:
    """
    The caller's UserStorageAccount row, created on first use. Read through the
    request.user related instance (and created with user=request.user) so the
    instance the login flow writes is also the instance later reads see.
    """
    account = getattr(request.user, 'storage_account', None)
    if account is None:
        account, _ = UserStorageAccount.objects.get_or_create(user=request.user)
    return account


class UserStorageLoginStartView(UserStorageView):
    throttle_classes = [LoginStartThrottle]

    def post(self, request):
        serializer = LoginStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            expires_in = login.start(request.user, serializer.validated_data['phone'],
                                     target_row=_my_account(request))
        except login.LoginError as exc:
            return _login_error(exc)
        return Response({'ok': True, 'expires_in': expires_in})


class UserStorageLoginVerifyView(UserStorageView):
    def post(self, request):
        serializer = LoginCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(login.verify_code(request.user, serializer.validated_data['code'],
                                              target_row=_my_account(request)))
        except login.LoginError as exc:
            return _login_error(exc)


class UserStorageLoginPasswordView(UserStorageView):
    def post(self, request):
        serializer = LoginPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(login.verify_password(request.user, serializer.validated_data['password'],
                                                  target_row=_my_account(request)))
        except login.LoginError as exc:
            return _login_error(exc)


class UserStorageLoginCancelView(UserStorageView):
    def post(self, request):
        login.cancel(target_row=_my_account(request))
        return Response({'ok': True})


class UserStorageTestView(UserStorageView):
    def post(self, request):
        account = getattr(request.user, 'storage_account', None)
        if not account or not account.has_session:
            return Response({'ok': False, 'reason': 'storage_not_connected'},
                            status=status.HTTP_400_BAD_REQUEST)
        ok, reason = health.check_health(account=account, force=True)
        return Response({'ok': ok, 'reason': reason})


class UserStorageDisconnectView(UserStorageView):
    """Drops the session locally. The user should also revoke it in Telegram; we log out best effort."""
    def post(self, request):
        account = getattr(request.user, 'storage_account', None)
        if account and account.has_session:
            try:
                login.logout_client(decrypt(account.session_string_enc))
            except Exception:
                pass
            account.session_string_enc = ''
            account.status = 'disconnected'
            account.save()
            credentials.invalidate(account_id=account.id)
            health.reset(key=f"user:{account.id}")
        return Response({'ok': True})


# -- User management (superuser) -------------------------------------------------------------------------

class AdminUserListPagination(PageNumberPagination):
    page_size = 50


def serialize_admin_user(user):
    account = getattr(user, 'storage_account', None)
    file_qs = account.files.all() if account else FileItem.objects.none()
    return {
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'is_active': user.is_active,
        'is_superuser': user.is_superuser,
        'date_joined': user.date_joined,
        'system_storage_allowed': user.system_storage_allowed,
        'can_use_system_storage': user.can_use_system_storage,
        'storage_quota': user.storage_quota,
        'storage_used': user.storage_used,
        'own': {
            'connected': bool(account and account.has_session),
            'status': account.status if account else 'disconnected',
            'reason': account.last_check_reason if account else '',
            'account_name': account.tg_display_name if account else '',
            'file_count': file_qs.count(),
            'bytes': file_qs.aggregate(total=Sum('size'))['total'] or 0,
        },
    }


class AdminUsersView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, ApiTokenScopePermission, IsStorageAdmin]
    pagination_class = AdminUserListPagination

    def get(self, request):
        qs = User.objects.all().order_by('id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(email__icontains=search) | Q(name__icontains=search))
        page = self.paginate_queryset(qs)
        results = [serialize_admin_user(u) for u in page]
        return self.get_paginated_response(results)


class AdminUserDetailView(StorageAdminView):
    def patch(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        fields = {}
        for field in ('system_storage_allowed', 'is_active'):
            if field in request.data:
                fields[field] = bool(request.data[field])
        if 'storage_quota' in request.data:
            raw = request.data['storage_quota']
            if raw is None:
                fields['storage_quota'] = None
            else:
                try:
                    quota = int(raw)
                except (TypeError, ValueError):
                    raise serializers.ValidationError({"storage_quota": "Must be null or an integer >= 0."})
                if quota < 0:
                    raise serializers.ValidationError({"storage_quota": "Must be null or an integer >= 0."})
                fields['storage_quota'] = quota

        if fields.get('is_active') is False and target.pk == request.user.pk:
            return Response({'error': 'Cannot deactivate yourself.'}, status=status.HTTP_400_BAD_REQUEST)

        changed = sorted(f for f, v in fields.items() if getattr(target, f) != v)
        if changed:
            for field in changed:
                setattr(target, field, fields[field])
            target.save(update_fields=changed)
            logger.info("User id=%s updated by admin id=%s fields=%s", target.pk, request.user.id, changed)
        return Response(serialize_admin_user(target))
