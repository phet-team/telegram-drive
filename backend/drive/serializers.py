from rest_framework import serializers
from django.contrib.auth import get_user_model
from drive.models import Folder, FileItem, UploadSession, UploadChunk, Permission, ShareLink, UserStarredItem
from drive.permissions import resolve_effective_role

User = get_user_model()


class FolderSerializer(serializers.ModelSerializer):
    owner_email = serializers.ReadOnlyField(source='owner.email')
    owner_name = serializers.ReadOnlyField(source='owner.name')
    owner_avatar = serializers.ReadOnlyField(source='owner.avatar_url')
    owner_telegram_id = serializers.ReadOnlyField(source='owner.telegram_id')
    parent_name = serializers.ReadOnlyField(source='parent.name')
    effective_role = serializers.SerializerMethodField()
    is_starred = serializers.SerializerMethodField()

    class Meta:
        model = Folder
        fields = [
            'id', 'name', 'parent', 'parent_name', 'owner_email', 'owner_name', 'owner_avatar', 'owner_telegram_id',
            'is_trashed', 'trashed_at', 'created_at', 'updated_at',
            'effective_role', 'is_starred'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'owner_email', 'owner_name', 'owner_avatar', 'owner_telegram_id', 'parent_name']

    def get_effective_role(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return resolve_effective_role(request.user, obj)
        return None

    def get_is_starred(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return UserStarredItem.objects.filter(user=request.user, folder=obj).exists()
        return False


class FileItemSerializer(serializers.ModelSerializer):
    owner_email = serializers.ReadOnlyField(source='owner.email')
    owner_name = serializers.ReadOnlyField(source='owner.name')
    owner_avatar = serializers.ReadOnlyField(source='owner.avatar_url')
    owner_telegram_id = serializers.ReadOnlyField(source='owner.telegram_id')
    folder_name = serializers.ReadOnlyField(source='folder.name')
    effective_role = serializers.SerializerMethodField()
    is_starred = serializers.SerializerMethodField()

    class Meta:
        model = FileItem
        fields = [
            'id', 'name', 'folder', 'folder_name', 'owner_email', 'owner_name', 'owner_avatar', 'owner_telegram_id', 'size',
            'mime_type', 'sha256', 'is_trashed', 'trashed_at',
            'created_at', 'updated_at', 'effective_role', 'is_starred'
        ]
        read_only_fields = ['id', 'size', 'mime_type', 'sha256', 'created_at', 'updated_at', 'owner_email', 'owner_name', 'owner_avatar', 'owner_telegram_id', 'folder_name']

    def get_effective_role(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return resolve_effective_role(request.user, obj)
        return None

    def get_is_starred(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return UserStarredItem.objects.filter(user=request.user, file=obj).exists()
        return False


class UploadSessionSerializer(serializers.ModelSerializer):
    uploaded_chunks_count = serializers.SerializerMethodField()

    class Meta:
        model = UploadSession
        fields = [
            'id', 'filename', 'mime_type', 'total_size', 'chunk_size',
            'total_chunks', 'expected_sha256', 'status', 'created_at',
            'expires_at', 'uploaded_chunks_count'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'expires_at']

    def get_uploaded_chunks_count(self, obj):
        return obj.uploaded_chunks.filter(status='UPLOADED').count()


class PermissionSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(write_only=True, required=False)
    grantee_email = serializers.ReadOnlyField(source='user.email')
    grantee_name = serializers.ReadOnlyField(source='user.name')
    grantee_avatar = serializers.ReadOnlyField(source='user.avatar_url')
    grantee_telegram_id = serializers.ReadOnlyField(source='user.telegram_id')

    class Meta:
        model = Permission
        fields = ['id', 'user_email', 'grantee_email', 'grantee_name', 'grantee_avatar', 'grantee_telegram_id', 'folder', 'file', 'role', 'created_at']
        read_only_fields = ['id', 'created_at', 'grantee_email', 'grantee_name', 'grantee_avatar', 'grantee_telegram_id']

    def validate_user_email(self, value):
        if not value:
            return None
        user = User.objects.filter(email__iexact=value).first()
        if not user:
            raise serializers.ValidationError("User with this email does not exist.")
        return user


class ShareLinkSerializer(serializers.ModelSerializer):
    has_password = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = ShareLink
        fields = [
            'id', 'token', 'folder', 'file', 'role',
            'expires_at', 'is_active', 'created_at', 'has_password', 'password'
        ]
        read_only_fields = ['id', 'token', 'created_at']

    def get_has_password(self, obj):
        return bool(obj.password_hash)
