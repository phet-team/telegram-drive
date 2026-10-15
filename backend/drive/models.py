import uuid
from django.db import models
from django.conf import settings
from django.db.models import Q, CheckConstraint, UniqueConstraint
from django.utils import timezone


class Folder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_folders')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subfolders')
    
    is_trashed = models.BooleanField(default=False, db_index=True)
    trashed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class FileItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True, blank=True, related_name='files')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_files')
    
    size = models.BigIntegerField(help_text="Total size in bytes")
    mime_type = models.CharField(max_length=255, default='application/octet-stream')
    sha256 = models.CharField(max_length=64, blank=True, default='')
    
    is_trashed = models.BooleanField(default=False, db_index=True)
    trashed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class FileChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file_item = models.ForeignKey(FileItem, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.IntegerField()
    telegram_message_id = models.BigIntegerField()
    telegram_file_id = models.CharField(max_length=512)
    chunk_size = models.BigIntegerField()
    sha256 = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        ordering = ['chunk_index']
        constraints = [
            UniqueConstraint(fields=['file_item', 'chunk_index'], name='unique_file_chunk_index')
        ]


class UploadSession(models.Model):
    STATUS_CHOICES = (
        ('UPLOADING', 'Uploading'),
        ('PROCESSING', 'Processing'),
        ('READY', 'Ready'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='upload_sessions')
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True, blank=True)
    filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=255, default='application/octet-stream')
    total_size = models.BigIntegerField()
    chunk_size = models.BigIntegerField(default=16 * 1024 * 1024)
    total_chunks = models.IntegerField()
    expected_sha256 = models.CharField(max_length=64, blank=True, default='')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='UPLOADING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at


class UploadChunk(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('UPLOADED', 'Uploaded'),
        ('FAILED', 'Failed'),
    )
    session = models.ForeignKey(UploadSession, on_delete=models.CASCADE, related_name='uploaded_chunks')
    chunk_index = models.IntegerField()
    chunk_size = models.BigIntegerField()
    telegram_message_id = models.BigIntegerField(null=True, blank=True)
    telegram_file_id = models.CharField(max_length=512, blank=True, default='')
    chunk_sha256 = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    class Meta:
        ordering = ['chunk_index']
        constraints = [
            UniqueConstraint(fields=['session', 'chunk_index'], name='unique_session_chunk_index')
        ]


class Permission(models.Model):
    ROLE_CHOICES = (
        ('editor', 'Editor'),
        ('viewer', 'Viewer'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='granted_permissions')
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True, blank=True, related_name='permissions')
    file = models.ForeignKey(FileItem, on_delete=models.CASCADE, null=True, blank=True, related_name='permissions')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            CheckConstraint(
                condition=(
                    (Q(file__isnull=False) & Q(folder__isnull=True)) |
                    (Q(file__isnull=True) & Q(folder__isnull=False))
                ),
                name='permission_target_exact_one'
            ),
            UniqueConstraint(fields=['user', 'file'], name='unique_user_file_permission'),
            UniqueConstraint(fields=['user', 'folder'], name='unique_user_folder_permission'),
        ]


class UserStarredItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='starred_items')
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True, blank=True, related_name='starred_by_users')
    file = models.ForeignKey(FileItem, on_delete=models.CASCADE, null=True, blank=True, related_name='starred_by_users')
    starred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            CheckConstraint(
                condition=(
                    (Q(file__isnull=False) & Q(folder__isnull=True)) |
                    (Q(file__isnull=True) & Q(folder__isnull=False))
                ),
                name='starred_target_exact_one'
            ),
            UniqueConstraint(fields=['user', 'file'], name='unique_user_file_starred'),
            UniqueConstraint(fields=['user', 'folder'], name='unique_user_folder_starred'),
        ]


class ShareLink(models.Model):
    ROLE_CHOICES = (
        ('editor', 'Editor'),
        ('viewer', 'Viewer'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.CharField(max_length=64, unique=True, db_index=True)
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True, blank=True, related_name='share_links')
    file = models.ForeignKey(FileItem, on_delete=models.CASCADE, null=True, blank=True, related_name='share_links')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')
    password_hash = models.CharField(max_length=255, blank=True, default='')
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return bool(self.expires_at and timezone.now() > self.expires_at)

    class Meta:
        constraints = [
            CheckConstraint(
                condition=(
                    (Q(file__isnull=False) & Q(folder__isnull=True)) |
                    (Q(file__isnull=True) & Q(folder__isnull=False))
                ),
                name='sharelink_target_exact_one'
            )
        ]
