import math
import hashlib
import secrets
import logging
from urllib.parse import quote
from datetime import timedelta
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction
from django.contrib.auth import get_user_model
from django.db.models import F, Q
from django.db.models.functions import Greatest
from django.http import HttpResponse, StreamingHttpResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, views, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
from django.views.decorators.clickjacking import xframe_options_exempt
from django.utils.decorators import method_decorator

from drive.models import (
    Folder, FileItem, FileChunk, UploadSession,
    UploadChunk, Permission, ShareLink, UserStarredItem
)
from drive.serializers import (
    FolderSerializer, FileItemSerializer, UploadSessionSerializer,
    PermissionSerializer, ShareLinkSerializer
)
from drive.permissions import (
    resolve_effective_role, can_read, can_write, can_delete_forever,
    can_share, validate_folder_move, get_accessible_folders, get_accessible_files,
    is_item_or_ancestor_trashed
)
from authentication.token_permissions import (
    get_api_token, enforce_token_subtree, is_in_subtree, ApiTokenScopePermission,
)
from storage_engine import health
from storage_engine.accounts import engine_for, resolve_upload_target
from storage_engine.errors import ContentUnavailable, StorageNotConnected, StorageUnavailable
from storage_engine.signed_token import generate_media_token, verify_media_token, parse_and_verify_media_token
from config.env_schema import config

logger = logging.getLogger(__name__)


def _release_used(user_pk, size):
    """Atomic `storage_used -= size` (floored at 0); never saves a stale User instance."""
    get_user_model().objects.filter(pk=user_pk).update(storage_used=Greatest(F('storage_used') - size, 0))


def _locked_user(user):
    """The requesting user's row under SELECT ... FOR UPDATE (call inside transaction.atomic)."""
    return get_user_model().objects.select_for_update().get(pk=user.pk)


def _refuse_if_system_grant_revoked(user, session):
    """
    A system-storage session opened before the admin revoked the grant must not keep writing:
    cancel it, release its reservation, then answer 409 storage_not_connected.
    """
    if session.storage_account_id is not None or user.can_use_system_storage:
        return
    with transaction.atomic():
        locked = UploadSession.objects.select_for_update().get(pk=session.pk)
        if locked.status == 'UPLOADING':
            get_user_model().objects.filter(pk=user.pk).update(
                storage_reserved=Greatest(F('storage_reserved') - locked.total_size, 0))
            locked.status = 'CANCELLED'
            locked.save(update_fields=['status', 'updated_at'])
    raise StorageNotConnected("Your access to the system storage was removed. Connect your Telegram account in Settings → My storage to upload.")


class FolderViewSet(viewsets.ModelViewSet):
    serializer_class = FolderSerializer
    permission_classes = [permissions.IsAuthenticated, ApiTokenScopePermission]

    def get_queryset(self):
        user = self.request.user
        token = get_api_token(self.request)
        if self.action == 'destroy':
            if user.is_superuser:
                return Folder.objects.all()
            return Folder.objects.filter(Q(owner=user) | Q(permissions__user=user))
        is_trashed = self.request.query_params.get('trashed', 'false').lower() == 'true'
        is_shared = self.request.query_params.get('shared', 'false').lower() == 'true'
        search = self.request.query_params.get('search', '').strip()
        # Crucial: Only filter parent for 'list' action; allow detail actions on any subfolder!
        if self.action == 'list':
            if token is not None and token.folder_id is not None:
                # Folder-restricted tokens: search/shared/trashed not allowed
                if search or is_shared or is_trashed:
                    raise PermissionDenied("API token cannot use search, shared or trashed filters.")
                parent_id = self.request.query_params.get('parent')
                root = token.folder
                if parent_id is None:
                    # Listing without parent returns only the token folder itself
                    return Folder.objects.filter(pk=root.pk)
                parent = get_object_or_404(Folder, pk=parent_id)
                if parent.id != root.id and not is_in_subtree(parent, root):
                    raise PermissionDenied("API token cannot list folders outside its folder.")
            if search:
                qs = get_accessible_folders(user, parent_id='ALL', is_trashed=is_trashed, is_shared=is_shared)
                if not is_shared:
                    qs = qs.filter(owner=user)
                else:
                    qs = qs.exclude(owner=user)
                return qs.filter(name__icontains=search).select_related('parent', 'owner')
            parent_id = self.request.query_params.get('parent')
            return get_accessible_folders(user, parent_id=parent_id, is_trashed=is_trashed, is_shared=is_shared)
        return get_accessible_folders(user, parent_id='ALL', is_trashed=is_trashed, is_shared=is_shared)

    def create(self, request, *args, **kwargs):
        token = get_api_token(request)
        if token is not None and token.folder_id is not None:
            parent_id = request.data.get('parent')
            if not parent_id:
                raise PermissionDenied("API token requires a parent folder inside its folder.")
            parent = get_object_or_404(Folder, pk=parent_id)
            if parent.id != token.folder_id and not is_in_subtree(parent, token.folder):
                raise PermissionDenied("API token cannot create folders outside its folder.")
        return super().create(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        folder = self.get_object()
        enforce_token_subtree(request, folder)
        return super().retrieve(request, *args, **kwargs)

    def perform_create(self, serializer):
        user = self.request.user
        name = get_valid_filename(serializer.validated_data.get('name', '').strip()) or 'Untitled folder'
        parent = serializer.validated_data.get('parent')
        if parent:
            if not can_write(user, parent):
                raise PermissionDenied("You do not have permission to create folders here.")
        serializer.save(owner=user, name=name)

    def update(self, request, *args, **kwargs):
        folder = self.get_object()
        if not can_write(request.user, folder):
            raise PermissionDenied("You do not have permission to edit this folder.")

        if 'parent' in request.data:
            target_parent_id = request.data.get('parent')
            target_folder = None
            if target_parent_id:
                target_folder = get_object_or_404(Folder, pk=target_parent_id)
                if not can_write(request.user, target_folder):
                    raise PermissionDenied("Permission denied on destination folder.")
            validate_folder_move(folder, target_folder)

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def move(self, request, pk=None):
        folder = self.get_object()
        if not can_write(request.user, folder):
            raise PermissionDenied("Permission denied on source folder.")

        target_parent_id = request.data.get('target_parent_id')
        target_folder = None
        if target_parent_id:
            target_folder = get_object_or_404(Folder, pk=target_parent_id)
            if not can_write(request.user, target_folder):
                raise PermissionDenied("Permission denied on destination folder.")

        validate_folder_move(folder, target_folder)
        folder.parent = target_folder
        folder.save(update_fields=['parent', 'updated_at'])
        return Response(FolderSerializer(folder, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def trash(self, request, pk=None):
        folder = self.get_object()
        if not can_write(request.user, folder):
            raise PermissionDenied("Permission denied to trash this folder.")
        folder.is_trashed = True
        folder.trashed_at = timezone.now()
        folder.save(update_fields=['is_trashed', 'trashed_at'])
        return Response({'message': 'Folder moved to trash'})

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        folder = get_object_or_404(Folder, pk=pk)
        if not can_write(request.user, folder):
            raise PermissionDenied("Permission denied to restore this folder.")
        folder.is_trashed = False
        folder.trashed_at = None
        folder.save(update_fields=['is_trashed', 'trashed_at'])
        return Response({'message': 'Folder restored from trash'})

    @action(detail=True, methods=['post'])
    def toggle_star(self, request, pk=None):
        folder = self.get_object()
        star, created = UserStarredItem.objects.get_or_create(user=request.user, folder=folder)
        if not created:
            star.delete()
            return Response({'is_starred': False})
        return Response({'is_starred': True})

    def destroy(self, request, *args, **kwargs):
        folder = self.get_object()
        if not can_delete_forever(request.user, folder):
            raise PermissionDenied("Only the folder owner can delete permanently.")

        # Folders that will really be deleted: the folder plus descendants owned by the requester.
        # Foreign subfolders are detached below and keep their whole subtree (and its files).
        all_folders = [folder]
        frontier = [folder]
        while frontier:
            sub = list(Folder.objects.filter(parent__in=frontier, owner=request.user))
            all_folders.extend(sub)
            frontier = sub

        # Cleanup Telegram chunks and quota for user's files inside, grouped by storage account.
        user_files = list(FileItem.objects.filter(folder__in=all_folders, owner=request.user))
        by_account = {}
        for f in user_files:
            by_account.setdefault(f.storage_account, []).append(f)

        # Pre-check health for every connected storage before deleting any message.
        for storage_account in by_account:
            if storage_account is not None and not storage_account.has_session:
                continue
            health.raise_if_known_down(key='system' if storage_account is None else f"user:{storage_account.id}")

        # Safeguard foreign items: detach them to user's root instead of cascade deleting!
        FileItem.objects.filter(folder__in=all_folders).exclude(owner=request.user).update(folder=None)
        Folder.objects.filter(parent__in=all_folders).exclude(owner=request.user).update(parent=None)

        for storage_account, group_files in by_account.items():
            if storage_account is not None and not storage_account.has_session:
                logger.warning(
                    "Storage disconnected for account %s; deleting DB records while leaving messages in user channel",
                    storage_account.id,
                )
                continue
            engine = engine_for(storage_account)
            for f in group_files:
                for c in f.chunks.all():
                    try:
                        engine.delete_chunk(c.telegram_message_id)
                    except Exception:
                        pass

        # Quota only tracks files in the system storage; a disconnected account's messages
        # stay in the user's own channel, so only system-file sizes are freed here.
        total_freed = sum(f.size for f in user_files if f.storage_account is None)
        if total_freed > 0:
            _release_used(request.user.pk, total_freed)

        return super().destroy(request, *args, **kwargs)


class FileItemViewSet(viewsets.ModelViewSet):
    serializer_class = FileItemSerializer
    permission_classes = [permissions.IsAuthenticated, ApiTokenScopePermission]

    def get_queryset(self):
        user = self.request.user
        token = get_api_token(self.request)
        if self.action == 'destroy':
            if user.is_superuser:
                return FileItem.objects.all()
            return FileItem.objects.filter(Q(owner=user) | Q(permissions__user=user))
        is_trashed = self.request.query_params.get('trashed', 'false').lower() == 'true'
        is_shared = self.request.query_params.get('shared', 'false').lower() == 'true'
        search = self.request.query_params.get('search', '').strip()
        # Crucial: Only filter folder for 'list' action; allow detail actions on any subfolder file!
        if self.action == 'list':
            if token is not None and token.folder_id is not None:
                # Folder-restricted tokens: search/shared/trashed not allowed
                if search or is_shared or is_trashed:
                    raise PermissionDenied("API token cannot use search, shared or trashed filters.")
                folder_id = self.request.query_params.get('folder')
                if not folder_id:
                    raise PermissionDenied("API token requires the folder parameter inside its folder.")
                folder = get_object_or_404(Folder, pk=folder_id)
                if folder.id != token.folder_id and not is_in_subtree(folder, token.folder):
                    raise PermissionDenied("API token cannot list files outside its folder.")
            if search:
                qs = get_accessible_files(user, folder_id='ALL', is_trashed=is_trashed, is_shared=is_shared)
                if not is_shared:
                    qs = qs.filter(owner=user)
                else:
                    qs = qs.exclude(owner=user)
                return qs.filter(name__icontains=search).select_related('folder', 'owner')
            folder_id = self.request.query_params.get('folder')
            return get_accessible_files(user, folder_id=folder_id, is_trashed=is_trashed, is_shared=is_shared)
        return get_accessible_files(user, folder_id='ALL', is_trashed=is_trashed, is_shared=is_shared)

    def retrieve(self, request, *args, **kwargs):
        file_item = self.get_object()
        enforce_token_subtree(request, file_item)
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def rename(self, request, pk=None):
        file_item = self.get_object()
        if not can_write(request.user, file_item):
            raise PermissionDenied("Permission denied to rename this file.")
        raw_name = request.data.get('name', '').strip()
        new_name = get_valid_filename(raw_name)
        if not new_name:
            raise ValidationError("File name cannot be empty or invalid.")
        file_item.name = new_name
        file_item.save(update_fields=['name', 'updated_at'])
        return Response(FileItemSerializer(file_item, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def move(self, request, pk=None):
        file_item = self.get_object()
        if not can_write(request.user, file_item):
            raise PermissionDenied("Permission denied on file.")

        target_folder_id = request.data.get('target_folder_id')
        target_folder = None
        if target_folder_id:
            target_folder = get_object_or_404(Folder, pk=target_folder_id)
            if not can_write(request.user, target_folder):
                raise PermissionDenied("Permission denied on destination folder.")

        file_item.folder = target_folder
        file_item.save(update_fields=['folder', 'updated_at'])
        return Response(FileItemSerializer(file_item, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def trash(self, request, pk=None):
        file_item = self.get_object()
        if not can_write(request.user, file_item):
            raise PermissionDenied("Permission denied to trash this file.")
        file_item.is_trashed = True
        file_item.trashed_at = timezone.now()
        file_item.save(update_fields=['is_trashed', 'trashed_at'])
        return Response({'message': 'File moved to trash'})

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        file_item = get_object_or_404(FileItem, pk=pk)
        if not can_write(request.user, file_item):
            raise PermissionDenied("Permission denied to restore this file.")
        file_item.is_trashed = False
        file_item.trashed_at = None
        file_item.save(update_fields=['is_trashed', 'trashed_at'])
        return Response({'message': 'File restored from trash'})

    @action(detail=True, methods=['post'])
    def toggle_star(self, request, pk=None):
        file_item = self.get_object()
        star, created = UserStarredItem.objects.get_or_create(user=request.user, file=file_item)
        if not created:
            star.delete()
            return Response({'is_starred': False})
        return Response({'is_starred': True})

    def update(self, request, *args, **kwargs):
        file_item = self.get_object()
        if not can_write(request.user, file_item):
            raise PermissionDenied("You do not have permission to edit this file.")

        if 'folder' in request.data:
            target_folder_id = request.data.get('folder')
            target_folder = None
            if target_folder_id:
                target_folder = get_object_or_404(Folder, pk=target_folder_id)
                if not can_write(request.user, target_folder):
                    raise PermissionDenied("Permission denied on destination folder.")

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def media_token(self, request, pk=None):
        """Generates short-lived signed media token for <video src>, download, or PDF tags"""
        file_item = self.get_object()
        if not can_read(request.user, file_item):
            raise PermissionDenied("Permission denied.")
        token = generate_media_token('user', str(request.user.id), str(file_item.id), expires_in_seconds=1800)
        return Response({'media_token': token})

    def destroy(self, request, *args, **kwargs):
        file_item = self.get_object()
        if not can_delete_forever(request.user, file_item):
            raise PermissionDenied("Only the file owner can delete permanently.")

        acc = file_item.storage_account
        if acc is not None and not acc.has_session:
            logger.warning(
                "Storage disconnected for account %s; deleting DB records while leaving messages in user channel",
                acc.id,
            )
            # Not a system file: the DB row goes away, quota untouched, messages stay in the channel.
            with transaction.atomic():
                file_item.delete()
        else:
            health.raise_if_known_down(key=f"user:{acc.id}" if acc else 'system')
            engine = engine_for(acc)
            chunks = list(file_item.chunks.all())
            file_size = file_item.size
            owner_pk = file_item.owner_id

            with transaction.atomic():
                file_item.delete()
                # Restore quota only for files that counted against the owner's system storage.
                if acc is None:
                    _release_used(owner_pk, file_size)

            # Best effort Telegram message cleanup
            try:
                for chunk in chunks:
                    engine.delete_chunk(chunk.telegram_message_id)
            except StorageUnavailable as exc:
                logger.warning(
                    "File %s deleted locally but storage messages could not be removed: %s",
                    file_item.id, exc.reason,
                )

        return Response({'message': 'File permanently deleted'})


class UploadViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated, ApiTokenScopePermission]

    def retrieve(self, request, pk=None):
        """Retrieves upload session status and list of successfully uploaded chunk indices for resumable uploads"""
        session = get_object_or_404(UploadSession, pk=pk, user=request.user)
        enforce_token_subtree(request, session.folder)
        uploaded_chunks = list(
            session.uploaded_chunks.filter(status='UPLOADED').values_list('chunk_index', flat=True)
        )
        return Response({
            'session_id': str(session.id),
            'status': session.status,
            'filename': session.filename,
            'total_size': session.total_size,
            'chunk_size': session.chunk_size,
            'total_chunks': session.total_chunks,
            'uploaded_chunks': uploaded_chunks,
            'is_expired': session.is_expired(),
        })

    @action(detail=False, methods=['post'])
    def initiate(self, request):
        user = request.user
        token = get_api_token(request)
        raw_name = request.data.get('filename', '').strip()
        filename = get_valid_filename(raw_name)
        try:
            total_size = int(request.data.get('total_size', 0))
        except (ValueError, TypeError):
            raise ValidationError("Invalid total_size.")

        if not filename or total_size <= 0:
            raise ValidationError("Invalid filename or total_size.")

        MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024 * 1024  # 2 TB ceiling per file
        if total_size > MAX_FILE_SIZE:
            raise ValidationError("File size exceeds maximum supported limit (2TB).")

        folder = None
        if folder_id := request.data.get('folder_id'):
            folder = get_object_or_404(Folder, pk=folder_id)
            if not can_write(user, folder):
                raise PermissionDenied("Cannot upload to this folder.")
        elif token is not None and token.folder_id is not None:
            raise PermissionDenied("API token requires folder_id inside its folder.")
        enforce_token_subtree(request, folder)

        expected_sha256 = request.data.get('expected_sha256', '')
        mime_type = request.data.get('mime_type', 'application/octet-stream')

        # Resolve where the bytes go: the user's own connected account, or None for the system
        # storage. A user with neither raises StorageNotConnected, handled as 409.
        target_account = resolve_upload_target(user)

        # Refuse early (503) when storage is known to be down: no quota reserved, no session created
        health.raise_if_known_down(key='system' if target_account is None else f"user:{target_account.id}")

        # 1. Quota is tracked only for system-storage uploads: atomic check & reservation
        with transaction.atomic():
            if target_account is None:
                user = _locked_user(user)
                if user.storage_quota is not None and user.available_quota < total_size:
                    raise ValidationError("Insufficient storage quota.")
                user.storage_reserved += total_size
                user.save(update_fields=['storage_reserved'])

            # Telegram MTProto Policy Limits:
            # - Hard floor: 1 MB (prevents FloodWait error from excessive message creation)
            # - Hard ceiling: 2000 MB (standard MTProto account file limit)
            TELEGRAM_HARD_FLOOR_BYTES = 1 * 1024 * 1024
            TELEGRAM_HARD_CEILING_BYTES = 2000 * 1024 * 1024

            server_min_bytes = max(TELEGRAM_HARD_FLOOR_BYTES, getattr(config, 'MIN_CHUNK_SIZE_MB', 4) * 1024 * 1024)
            server_max_bytes = min(TELEGRAM_HARD_CEILING_BYTES, getattr(config, 'MAX_CHUNK_SIZE_MB', 32) * 1024 * 1024)
            server_default_bytes = getattr(config, 'DEFAULT_CHUNK_SIZE_MB', 8) * 1024 * 1024

            req_chunk_size = request.data.get('chunk_size')
            if req_chunk_size:
                try:
                    candidate_chunk = int(req_chunk_size)
                except (ValueError, TypeError):
                    candidate_chunk = server_default_bytes
            else:
                candidate_chunk = server_default_bytes

            # Clamp candidate within server bounds (which strictly obey Telegram policies)
            clamped_chunk = max(server_min_bytes, min(candidate_chunk, server_max_bytes))

            # Telegram MTProto requires parts to align to 1024 bytes (1 KB)
            chunk_size = (clamped_chunk // 1024) * 1024
            total_chunks = max(1, math.ceil(total_size / chunk_size))

            session = UploadSession.objects.create(
                user=user,
                folder=folder,
                filename=filename,
                mime_type=mime_type,
                total_size=total_size,
                chunk_size=chunk_size,
                total_chunks=total_chunks,
                expected_sha256=expected_sha256,
                expires_at=timezone.now() + timedelta(hours=24),
                storage_account=target_account
            )

        return Response({
            'session_id': str(session.id),
            'chunk_size': chunk_size,
            'total_chunks': total_chunks
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['put'], url_path='chunks/(?P<chunk_index>[0-9]+)')
    def upload_chunk(self, request, pk=None, chunk_index=None):
        session = get_object_or_404(UploadSession, pk=pk, user=request.user)
        enforce_token_subtree(request, session.folder)
        if session.status != 'UPLOADING' or session.is_expired():
            raise ValidationError("Upload session is expired or not active.")

        idx = int(chunk_index)
        if idx < 0 or idx >= session.total_chunks:
            raise ValidationError("Invalid chunk_index.")

        chunk_data = request.body
        if not chunk_data:
            raise ValidationError("No chunk data received.")

        # Hard limit chunk payload to 16MB + 4KB to strictly protect VPS memory
        if len(chunk_data) > session.chunk_size + 4096:
            raise ValidationError("Chunk payload exceeds session chunk size limit.")

        _refuse_if_system_grant_revoked(request.user, session)
        chunk_hash = hashlib.sha256(chunk_data).hexdigest()
        engine = engine_for(session.storage_account)

        # Upload to Telegram or Mock Storage
        msg_id, file_id = engine.upload_chunk(
            chunk_data,
            f"{session.id}_{idx}_{session.filename}"
        )

        # Idempotent record update
        UploadChunk.objects.update_or_create(
            session=session,
            chunk_index=idx,
            defaults={
                'chunk_size': len(chunk_data),
                'telegram_message_id': msg_id,
                'telegram_file_id': file_id,
                'chunk_sha256': chunk_hash,
                'status': 'UPLOADED'
            }
        )

        return Response({'status': 'Chunk uploaded', 'chunk_index': idx})

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        session = get_object_or_404(UploadSession, pk=pk, user=request.user)
        enforce_token_subtree(request, session.folder)
        if session.folder:
            if not can_write(request.user, session.folder):
                raise PermissionDenied("You do not have permission to write to destination folder.")
            if is_item_or_ancestor_trashed(session.folder):
                raise PermissionDenied("Destination folder is in trash.")

        if session.status != 'UPLOADING':
            raise ValidationError("Upload session is not in UPLOADING state.")
        _refuse_if_system_grant_revoked(request.user, session)

        uploaded_chunks = list(session.uploaded_chunks.filter(status='UPLOADED').order_by('chunk_index'))
        if len(uploaded_chunks) != session.total_chunks:
            raise ValidationError(f"Missing chunks. Uploaded: {len(uploaded_chunks)}/{session.total_chunks}")

        # Strict Quota Integrity Verification: verify sum of actual chunks matches declared total_size
        actual_total_size = sum(c.chunk_size for c in uploaded_chunks)
        if actual_total_size != session.total_size:
            raise ValidationError(
                f"Chunk size total ({actual_total_size}) does not match declared session total ({session.total_size})."
            )

        with transaction.atomic():
            user = _locked_user(request.user)
            # Re-check under the lock: a concurrent complete/cancel may have finished this session.
            session = UploadSession.objects.select_for_update().get(pk=session.pk)
            if session.status != 'UPLOADING':
                raise ValidationError("Upload session is not in UPLOADING state.")

            replace_file_id = request.data.get('replace_file_id')
            old_file = None
            if replace_file_id:
                old_file = FileItem.objects.filter(pk=replace_file_id, owner=user, is_trashed=False).first()

            if old_file:
                # Delete the old chunks from whichever storage currently holds them.
                old_acc = old_file.storage_account
                if old_acc is not None and not old_acc.has_session:
                    logger.warning(
                        "Storage disconnected for account %s; deleting DB records while leaving messages in user channel",
                        old_acc.id,
                    )
                else:
                    old_engine = engine_for(old_acc)
                    for oc in old_file.chunks.all():
                        try:
                            old_engine.delete_chunk(oc.telegram_message_id)
                        except Exception:
                            pass
                old_file.chunks.all().delete()

                # Quota: only the system-storage side of the swap touches the owner's counters.
                if session.storage_account is None:
                    user.storage_reserved = max(0, user.storage_reserved - session.total_size)
                    user.storage_used = max(0, user.storage_used + session.total_size)
                if old_file.storage_account is None:
                    user.storage_used = max(0, user.storage_used - old_file.size)
                user.storage_used = max(0, user.storage_used)
                user.save(update_fields=['storage_reserved', 'storage_used'])

                # Update existing FileItem, repointing it to the upload's storage account.
                old_file.name = session.filename
                old_file.size = session.total_size
                old_file.mime_type = session.mime_type
                old_file.sha256 = session.expected_sha256
                old_file.storage_account = session.storage_account
                old_file.save()
                file_item = old_file
            else:
                # Atomically adjust quota (system storage only)
                if session.storage_account is None:
                    user.storage_reserved = max(0, user.storage_reserved - session.total_size)
                    user.storage_used += session.total_size
                    user.save(update_fields=['storage_reserved', 'storage_used'])

                # Create FileItem
                file_item = FileItem.objects.create(
                    name=session.filename,
                    folder=session.folder,
                    owner=user,
                    size=session.total_size,
                    mime_type=session.mime_type,
                    sha256=session.expected_sha256,
                    storage_account=session.storage_account
                )

            # Map chunks
            file_chunks = [
                FileChunk(
                    file_item=file_item,
                    chunk_index=c.chunk_index,
                    telegram_message_id=c.telegram_message_id,
                    telegram_file_id=c.telegram_file_id,
                    chunk_size=c.chunk_size,
                    sha256=c.chunk_sha256
                )
                for c in uploaded_chunks
            ]
            FileChunk.objects.bulk_create(file_chunks)

            session.status = 'READY'
            session.save(update_fields=['status', 'updated_at'])

        return Response(FileItemSerializer(file_item, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancels an active upload session and releases reserved storage quota"""
        session = get_object_or_404(UploadSession, pk=pk, user=request.user)
        if session.status in ['READY', 'CANCELLED']:
            return Response({'message': f'Session already {session.status}'})

        with transaction.atomic():
            user = _locked_user(request.user)
            session = UploadSession.objects.select_for_update().get(pk=session.pk)
            if session.status in ['READY', 'CANCELLED']:
                return Response({'message': f'Session already {session.status}'})
            # Reserved bytes were only taken for system-storage uploads.
            if session.storage_account is None:
                user.storage_reserved = max(0, user.storage_reserved - session.total_size)
                user.save(update_fields=['storage_reserved'])

            session.status = 'CANCELLED'
            session.save(update_fields=['status', 'updated_at'])

        return Response({'message': 'Upload session cancelled, reserved quota released'})


@method_decorator(xframe_options_exempt, name='dispatch')
class FileStreamView(views.APIView):
    """
    HTTP 206 Partial Content Range Streaming Proxy.
    Adheres strictly to RFC 9110 for seeking in video/audio and large files.
    """
    permission_classes = [permissions.AllowAny, ApiTokenScopePermission]

    def get(self, request, pk):
        file_item = get_object_or_404(FileItem, pk=pk)

        # Trashed files or files inside trashed folders cannot be streamed
        if file_item.is_trashed or is_item_or_ancestor_trashed(file_item):
            raise Http404("File not found or in trash.")

        # Auth verification: either user has permission OR valid signed media token
        authorized = False
        if request.user.is_authenticated and can_read(request.user, file_item):
            authorized = True
        else:
            token = request.query_params.get('token')
            if token:
                parsed = parse_and_verify_media_token(token, str(file_item.id))
                if parsed:
                    if parsed.get('grant_type') == 'user':
                        from django.contrib.auth import get_user_model
                        grantee = get_user_model().objects.filter(id=parsed['grant_id']).first()
                        if grantee and can_read(grantee, file_item):
                            authorized = True
                    elif parsed.get('grant_type') == 'share':
                        share = ShareLink.objects.filter(id=parsed['grant_id'], is_active=True).first()
                        if share and not share.is_expired():
                            target = share.file or share.folder
                            if target and not is_item_or_ancestor_trashed(target):
                                if share.file_id == file_item.id:
                                    authorized = True
                                elif share.folder_id:
                                    curr = file_item.folder
                                    while curr:
                                        if curr.id == share.folder_id:
                                            authorized = True
                                            break
                                        curr = curr.parent
                    elif parsed.get('grant_type') == 'legacy':
                        if verify_media_token(file_item.owner_id, str(file_item.id), token):
                            authorized = True

        if not authorized:
            raise PermissionDenied("You do not have permission to access this file.")

        etag = f'"{file_item.sha256 or str(file_item.id)}"'
        if_none_match = request.headers.get('If-None-Match')
        if if_none_match and if_none_match == etag and not request.headers.get('Range'):
            resp = HttpResponse(status=304)
            resp['ETag'] = etag
            resp['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
            resp['Vary'] = 'Authorization, Range'
            return resp

        engine = engine_for(file_item.storage_account)
        chunks_qs = list(file_item.chunks.order_by('chunk_index'))
        if not chunks_qs:
            raise Http404("File content not found.")

        def detect_actual_mime(data_header: bytes, declared_mime: str) -> str:
            if data_header.startswith(b'\xff\xd8\xff'):
                return 'image/jpeg'
            if data_header.startswith(b'\x89PNG\r\n\x1a\n'):
                return 'image/png'
            if data_header.startswith(b'GIF87a') or data_header.startswith(b'GIF89a'):
                return 'image/gif'
            if data_header.startswith(b'RIFF') and len(data_header) >= 12 and data_header[8:12] == b'WEBP':
                return 'image/webp'
            return declared_mime

        range_header = request.headers.get('Range')

        # Single-chunk files (all images, audio clips, PDFs and documents <= 16MB)
        if len(chunks_qs) == 1:
            chunk = chunks_qs[0]
            try:
                chunk_data = engine.download_chunk(chunk.telegram_file_id, chunk.telegram_message_id)
            except (StorageUnavailable, ContentUnavailable):
                raise  # 503 / 410 via the DRF exception handler
            except Exception as e:
                logger.error(f"Failed downloading chunk for file {file_item.id}: {e}")
                return HttpResponse(b"Failed to retrieve file content from storage.", status=502, content_type="text/plain")

            actual_total_size = len(chunk_data)
            mime_type = detect_actual_mime(chunk_data[:16], file_item.mime_type)

            if range_header and range_header.startswith('bytes='):
                range_spec = range_header[6:].strip()
                parts = range_spec.split('-')
                try:
                    if parts[0] and parts[1]:
                        start = int(parts[0])
                        end = min(int(parts[1]), actual_total_size - 1)
                    elif parts[0] and not parts[1]:
                        start = int(parts[0])
                        end = actual_total_size - 1
                    elif not parts[0] and parts[1]:
                        suffix_length = int(parts[1])
                        start = max(0, actual_total_size - suffix_length)
                        end = actual_total_size - 1
                    else:
                        raise ValueError
                except (ValueError, IndexError):
                    resp = HttpResponse(status=416)
                    resp['Content-Range'] = f'bytes */{actual_total_size}'
                    return resp

                if start > end or start >= actual_total_size:
                    resp = HttpResponse(status=416)
                    resp['Content-Range'] = f'bytes */{actual_total_size}'
                    return resp

                slice_data = chunk_data[start:end + 1]
                response = StreamingHttpResponse(iter([slice_data]), status=206, content_type=mime_type)
                response['Content-Range'] = f'bytes {start}-{end}/{actual_total_size}'
                response['Content-Length'] = str(len(slice_data))
            else:
                response = StreamingHttpResponse(iter([chunk_data]), status=200, content_type=mime_type)
                response['Content-Length'] = str(actual_total_size)
        else:
            # Multi-chunk files (large videos, archives > 16MB)
            chunk_spans = []
            offset = 0
            for c in chunks_qs:
                c_len = c.chunk_size
                chunk_spans.append((offset, offset + c_len, c))
                offset += c_len
            total_size = offset or file_item.size

            if range_header and range_header.startswith('bytes='):
                range_spec = range_header[6:].strip()
                parts = range_spec.split('-')
                try:
                    if parts[0] and parts[1]:
                        start = int(parts[0])
                        end = min(int(parts[1]), total_size - 1)
                    elif parts[0] and not parts[1]:
                        start = int(parts[0])
                        end = total_size - 1
                    elif not parts[0] and parts[1]:
                        suffix_length = int(parts[1])
                        start = max(0, total_size - suffix_length)
                        end = total_size - 1
                    else:
                        raise ValueError
                except (ValueError, IndexError):
                    resp = HttpResponse(status=416)
                    resp['Content-Range'] = f'bytes */{total_size}'
                    return resp

                if start > end or start >= total_size:
                    resp = HttpResponse(status=416)
                    resp['Content-Range'] = f'bytes */{total_size}'
                    return resp

                content_length = (end - start) + 1
                status_code = 206
            else:
                start = 0
                end = total_size - 1
                content_length = total_size
                status_code = 200

            # Fetch the first needed chunk now (it stays in the engine's LRU cache) so a storage
            # problem becomes a proper 503/410 instead of a truncated 200/206 body.
            for c_start, c_end, chunk in chunk_spans:
                if c_end > start and c_start <= end:
                    try:
                        engine.download_chunk(chunk.telegram_file_id, chunk.telegram_message_id)
                    except (StorageUnavailable, ContentUnavailable):
                        raise
                    except Exception as e:
                        logger.error(f"Failed downloading chunk {chunk.chunk_index} for file {file_item.id}: {e}")
                        return HttpResponse(b"Failed to retrieve file content from storage.", status=502, content_type="text/plain")
                    break

            def stream_generator():
                for c_start, c_end, chunk in chunk_spans:
                    if c_end <= start or c_start > end:
                        continue
                    try:
                        chunk_data = engine.download_chunk(chunk.telegram_file_id, chunk.telegram_message_id)
                    except Exception as e:
                        logger.error(f"Stream interrupted during chunk {chunk.chunk_index}: {e}")
                        break
                    slice_s = max(0, start - c_start)
                    slice_e = min(len(chunk_data), end - c_start + 1)
                    if slice_e > slice_s:
                        yield chunk_data[slice_s:slice_e]

            response = StreamingHttpResponse(
                stream_generator(),
                status=status_code,
                content_type=file_item.mime_type
            )
            response['Content-Length'] = str(content_length)
            if status_code == 206:
                response['Content-Range'] = f'bytes {start}-{end}/{total_size}'
        
        # Dangerous scriptable mime types that require sandbox isolation and forced attachment (Anti-XSS)
        DANGEROUS_MIME_TYPES = {
            'image/svg+xml', 'text/html', 'application/xhtml+xml',
            'text/xml', 'application/xml', 'application/javascript', 'text/javascript'
        }
        is_dangerous_mime = file_item.mime_type.lower() in DANGEROUS_MIME_TYPES

        # Safe Content-Disposition escaping (RFC 6266 / RFC 5987 with Thai/Unicode support)
        is_download = request.query_params.get('download') == '1' or is_dangerous_mime
        disposition_type = 'attachment' if is_download else 'inline'
        
        ascii_filename = file_item.name.encode('ascii', 'ignore').decode('ascii').replace('"', '\\"') or 'file'
        encoded_filename = quote(file_item.name.encode('utf-8'))
        response['Content-Disposition'] = f"{disposition_type}; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}"

        if is_dangerous_mime:
            response['Content-Security-Policy'] = "sandbox; default-src 'none'; style-src 'unsafe-inline'"

        response.xframe_options_exempt = True
        if 'X-Frame-Options' in response:
            del response['X-Frame-Options']
        return response


class ShareViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, ApiTokenScopePermission]
    serializer_class = ShareLinkSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return ShareLink.objects.none()
        links = ShareLink.objects.all()
        accessible_ids = []
        for sl in links:
            target = sl.file or sl.folder
            if target and can_share(user, target):
                accessible_ids.append(sl.id)
        return ShareLink.objects.filter(id__in=accessible_ids)

    def create(self, request, *args, **kwargs):
        folder_id = request.data.get('folder')
        file_id = request.data.get('file')
        role = request.data.get('role', 'viewer')
        if role not in ('viewer', 'editor'):
            raise ValidationError({'role': "Invalid role. Role must be 'viewer' or 'editor'."})

        if bool(folder_id) == bool(file_id):
            raise ValidationError("Exactly one of folder or file must be specified.")

        password = request.data.get('password', '')
        expires_at = request.data.get('expires_at')

        item = None
        if folder_id:
            item = get_object_or_404(Folder, pk=folder_id)
        elif file_id:
            item = get_object_or_404(FileItem, pk=file_id)

        if not can_share(request.user, item):
            raise PermissionDenied("You do not have permission to share this item.")

        token = secrets.token_urlsafe(32)
        password_hash = ''
        if password:
            password_hash = make_password(password)

        share_link = ShareLink.objects.create(
            token=token,
            folder=item if isinstance(item, Folder) else None,
            file=item if isinstance(item, FileItem) else None,
            role=role,
            password_hash=password_hash,
            expires_at=expires_at
        )

        return Response(ShareLinkSerializer(share_link).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        share_link = self.get_object()
        target = share_link.file or share_link.folder
        if not can_share(request.user, target):
            raise PermissionDenied("Permission denied.")

        # Disallow mutating target
        if 'file' in request.data:
            req_file = request.data.get('file')
            if req_file and str(req_file) != str(share_link.file_id):
                raise ValidationError("Share link target cannot be modified.")
        if 'folder' in request.data:
            req_folder = request.data.get('folder')
            if req_folder and str(req_folder) != str(share_link.folder_id):
                raise ValidationError("Share link target cannot be modified.")

        # Password update
        if 'password' in request.data:
            new_pwd = request.data.get('password')
            share_link.password_hash = make_password(new_pwd) if new_pwd else ''
            share_link.save(update_fields=['password_hash'])

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)


class PermissionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, ApiTokenScopePermission]
    serializer_class = PermissionSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Permission.objects.none()
        qs = Permission.objects.all()
        file_id = self.request.query_params.get('file')
        folder_id = self.request.query_params.get('folder')
        if file_id:
            qs = qs.filter(file_id=file_id)
        elif folder_id:
            qs = qs.filter(folder_id=folder_id)

        allowed_ids = []
        for p in qs:
            target = p.file or p.folder
            if target and can_share(user, target):
                allowed_ids.append(p.id)
        return qs.filter(id__in=allowed_ids)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_user = serializer.validated_data.get('user_email')
        if not target_user:
            raise ValidationError({'user_email': "User email is required."})
        folder = serializer.validated_data.get('folder')
        file_item = serializer.validated_data.get('file')
        role = serializer.validated_data.get('role', 'viewer')

        target = file_item or folder
        if not target:
            raise ValidationError("Must specify either file or folder.")
        if not can_share(request.user, target):
            raise PermissionDenied("You do not have permission to share this item.")
        if target.owner_id == target_user.id:
            raise ValidationError("Cannot assign permission to item owner.")

        perm, created = Permission.objects.update_or_create(
            user=target_user,
            file=file_item,
            folder=folder,
            defaults={'role': role}
        )
        return Response(PermissionSerializer(perm).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        perm = self.get_object()
        target = perm.file or perm.folder
        if not can_share(request.user, target):
            raise PermissionDenied("You do not have permission to edit access.")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        perm = self.get_object()
        target = perm.file or perm.folder
        if not can_share(request.user, target):
            raise PermissionDenied("You do not have permission to revoke access.")
        perm.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublicShareView(views.APIView):
    """Public endpoint to view/access shared files or folders without login"""
    permission_classes = [permissions.AllowAny, ApiTokenScopePermission]

    def get(self, request, token):
        share_link = get_object_or_404(ShareLink, token=token, is_active=True)
        if share_link.expires_at and timezone.now() > share_link.expires_at:
            raise NotFound("This share link has expired.")

        target = share_link.file or share_link.folder
        if not target or is_item_or_ancestor_trashed(target):
            raise NotFound("This item has been moved to trash.")

        password = request.query_params.get('password', '')
        if share_link.password_hash:
            if not password or not check_password(password, share_link.password_hash):
                return Response({'error': 'Password required or incorrect'}, status=status.HTTP_403_FORBIDDEN)

        data = {
            'token': share_link.token,
            'role': share_link.role,
            'is_folder': bool(share_link.folder),
        }
        if share_link.file:
            data['file'] = FileItemSerializer(share_link.file, context={'request': request}).data
            # Generate temporary media token for preview/download
            data['media_token'] = generate_media_token('share', str(share_link.id), str(share_link.file.id), expires_in_seconds=3600)
        elif share_link.folder:
            requested_folder_id = request.query_params.get('folder')
            current_folder = share_link.folder
            if requested_folder_id and str(requested_folder_id) != str(share_link.folder.id):
                target_subfolder = get_object_or_404(Folder, pk=requested_folder_id, is_trashed=False)
                # Verify target_subfolder is a descendant of share_link.folder (anti-IDOR)
                curr = target_subfolder
                is_descendant = False
                while curr:
                    if curr.id == share_link.folder.id:
                        is_descendant = True
                        break
                    curr = curr.parent
                if not is_descendant:
                    raise PermissionDenied("You do not have permission to view this subfolder.")
                current_folder = target_subfolder

            # Build breadcrumbs from root shared folder down to current_folder
            breadcrumbs = []
            curr = current_folder
            while curr and curr.id != share_link.folder.id:
                breadcrumbs.append({'id': str(curr.id), 'name': curr.name})
                curr = curr.parent
            breadcrumbs.append({'id': str(share_link.folder.id), 'name': share_link.folder.name})
            breadcrumbs.reverse()

            data['folder'] = FolderSerializer(share_link.folder, context={'request': request}).data
            data['current_folder'] = FolderSerializer(current_folder, context={'request': request}).data
            data['breadcrumbs'] = breadcrumbs
            data['subfolders'] = FolderSerializer(current_folder.subfolders.filter(is_trashed=False), many=True, context={'request': request}).data
            files_data = []
            for f in current_folder.files.filter(is_trashed=False):
                f_data = FileItemSerializer(f, context={'request': request}).data
                f_data['media_token'] = generate_media_token('share', str(share_link.id), str(f.id), expires_in_seconds=3600)
                files_data.append(f_data)
            data['files'] = files_data

        return Response(data)
