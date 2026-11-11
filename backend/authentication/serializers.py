from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password

from authentication.models import ApiToken
from drive.models import Folder
from drive.permissions import can_write

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    available_quota = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'name', 'avatar_url',
            'storage_used', 'storage_reserved', 'storage_quota',
            'available_quota', 'telegram_id', 'google_sub', 'date_joined', 'is_superuser'
        ]
        read_only_fields = ['id', 'is_superuser', 'storage_used', 'storage_reserved', 'storage_quota', 'date_joined']


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            name=validated_data.get('name', '')
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email', '').lower()
        password = attrs.get('password')

        user = authenticate(username=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("Account is disabled.")

        attrs['user'] = user
        return attrs


class TelegramAuthSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    first_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    last_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    username = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    photo_url = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    auth_date = serializers.IntegerField(required=False)
    hash = serializers.CharField(required=False)
    is_dev_mock = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get('is_dev_mock'):
            if not attrs.get('id') or not attrs.get('auth_date') or not attrs.get('hash'):
                raise serializers.ValidationError("Missing required Telegram auth fields (id, auth_date, hash).")
        return attrs


class GoogleAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField()


class ApiTokenSerializer(serializers.ModelSerializer):
    folder = serializers.SerializerMethodField()

    class Meta:
        model = ApiToken
        fields = [
            'id', 'name', 'prefix', 'scopes', 'folder',
            'created_at', 'last_used_at', 'last_used_ip', 'revoked_at',
        ]
        read_only_fields = fields

    def get_folder(self, obj):
        if obj.folder is None:
            return None
        return {'id': str(obj.folder.id), 'name': obj.folder.name}


class ApiTokenCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    scopes = serializers.ListField(child=serializers.CharField(max_length=64), allow_empty=False)
    folder_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_scopes(self, value):
        if not value:
            raise serializers.ValidationError("At least one scope is required.")
        invalid = [s for s in value if s not in ApiToken.ALLOWED_SCOPES]
        if invalid:
            raise serializers.ValidationError(f"Invalid scopes: {', '.join(invalid)}")
        # de-duplicate while preserving order
        seen = set()
        return [s for s in value if not (s in seen or seen.add(s))]

    def validate(self, attrs):
        request = self.context['request']
        folder_id = attrs.get('folder_id')
        if folder_id:
            folder = Folder.objects.filter(pk=folder_id).first()
            if not folder:
                raise serializers.ValidationError({"folder_id": "Folder not found."})
            if not can_write(request.user, folder):
                raise serializers.ValidationError({"folder_id": "You do not have permission to use this folder."})
            attrs['folder'] = folder
        else:
            attrs['folder'] = None

        active = ApiToken.objects.filter(user=request.user, revoked_at__isnull=True).count()
        if active >= ApiToken.MAX_ACTIVE_TOKENS:
            raise serializers.ValidationError(
                f"Maximum of {ApiToken.MAX_ACTIVE_TOKENS} active API tokens reached."
            )
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        plaintext = ApiToken.generate_plaintext()
        token = ApiToken.objects.create(
            user=request.user,
            name=validated_data['name'].strip() or 'API token',
            prefix=plaintext[:12],
            token_hash=ApiToken.hash_token(plaintext),
            scopes=validated_data['scopes'],
            folder=validated_data.get('folder'),
        )
        token.set_plaintext(plaintext)
        return token