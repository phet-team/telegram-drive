from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    available_quota = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'name', 'avatar_url',
            'storage_used', 'storage_reserved', 'storage_quota',
            'available_quota', 'telegram_id', 'google_sub', 'date_joined'
        ]
        read_only_fields = ['id', 'storage_used', 'storage_reserved', 'storage_quota', 'date_joined']


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
