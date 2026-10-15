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
from django.db.models import Q
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
from storage_engine.client import get_storage_engine
from storage_engine.signed_token import generate_media_token, verify_media_token, parse_and_verify_media_token
from config.env_schema import config

logger = logging.getLogger(__name__)


class FolderViewSet(viewsets.ModelViewSet):
    serializer_class = FolderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if self.action == 'destroy':
            if user.is_superuser:
                return Folder.objects.all()
            return Folder.objects.filter(Q(owner=user) | Q(permissions__user=user))
        is_trashed = self.request.query_params.get('trashed', 'false').lower() == 'true'
        is_shared = self.request.query_params.get('shared', 'false').lower() == 'true'
        search = self.request.query_params.get('search', '').strip()
        # Crucial: Only filter parent for 'list' action; allow detail actions on any subfolder!
        if self.action == 'list':
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

        # Collect all descendant folders (including self)
        all_folders = [folder]
        frontier = [folder]
        while frontier:
            sub = list(Folder.objects.filter(parent__in=frontier))
            all_folders.extend(sub)
            frontier = sub

        # Safeguard foreign items: detach them to user's root instead of cascade deleting!
        FileItem.objects.filter(folder__in=all_folders).exclude(owner=request.user).update(folder=None)
        Folder.objects.filter(parent__in=all_folders).exclude(owner=request.user).update(parent=None)

        # Cleanup Telegram chunks and quota for user's files inside
        engine = get_storage_engine()
        user_files = list(FileItem.objects.filter(folder__in=all_folders, owner=request.user))
        total_freed = sum(f.size for f in user_files)
        for f in user_files:
            for c in f.chunks.all():
                try:
                    engine.delete_chunk(c.telegram_message_id)
                except Exception:
                    pass
        if total_freed > 0:
            request.user.storage_used = max(0, request.user.storage_used - total_freed)
            request.user.save(update_fields=['storage_used'])

        return super().destroy(request, *args, **kwargs)


class FileItemViewSet(viewsets.ModelViewSet):
    serializer_class = FileItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if self.action == 'destroy':
            if user.is_superuser:
                return FileItem.objects.all()
            return FileItem.objects.filter(Q(owner=user) | Q(permissions__user=user))
        is_trashed = self.request.query_params.get('trashed', 'false').lower() == 'true'
        is_shared = self.request.query_params.get('shared', 'false').lower() == 'true'
        search = self.request.query_params.get('search', '').strip()
        # Crucial: Only filter folder for 'list' action; allow detail actions on any subfolder file!
        if self.action == 'list':
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

        # In-System hard delete & Best-effort Telegram deleteMessage
        engine = get_storage_engine()
        chunks = list(file_item.chunks.all())
        file_size = file_item.size
        owner = file_item.owner

        with transaction.atomic():
            file_item.delete()
            # Restore user storage quota
            owner.storage_used = max(0, owner.storage_used - file_size)
            owner.save(update_fields=['storage_used'])

        # Best effort Telegram message cleanup
        for chunk in chunks:
            engine.delete_chunk(chunk.telegram_message_id)

        return Response({'message': 'File permanently deleted'})


class UploadViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def retrieve(self, request, pk=None):
        """Retrieves upload session status and list of successfully uploaded chunk indices for resumable uploads"""
        session = get_object_or_404(UploadSession, pk=pk, user=request.user)
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

        expected_sha256 = request.data.get('expected_sha256', '')
        mime_type = request.data.get('mime_type', 'application/octet-stream')

        # 1. Atomic quota check & reservation (if quota is configured)
        with transaction.atomic():
            user.refresh_from_db()
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
                expires_at=timezone.now() + timedelta(hours=24)
            )

        return Response({
            'session_id': str(session.id),
            'chunk_size': chunk_size,
            'total_chunks': total_chunks
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['put'], url_path='chunks/(?P<chunk_index>[0-9]+)')
    def upload_chunk(self, request, pk=None, chunk_index=None):
        session = get_object_or_404(UploadSession, pk=pk, user=request.user)
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

        chunk_hash = hashlib.sha256(chunk_data).hexdigest()
        engine = get_storage_engine()

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
        if session.folder:
            if not can_write(request.user, session.folder):
                raise PermissionDenied("You do not have permission to write to destination folder.")
            if is_item_or_ancestor_trashed(session.folder):
                raise PermissionDenied("Destination folder is in trash.")

        if session.status != 'UPLOADING':
            raise ValidationError("Upload session is not in UPLOADING state.")

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
            user = request.user
            user.refresh_from_db()

            engine = get_storage_engine()
            replace_file_id = request.data.get('replace_file_id')
            old_file = None
            if replace_file_id:
                old_file = FileItem.objects.filter(pk=replace_file_id, owner=user, is_trashed=False).first()

            if old_file:
                size_diff = session.total_size - old_file.size
                user.storage_reserved = max(0, user.storage_reserved - session.total_size)
                user.storage_used = max(0, user.storage_used + size_diff)
                user.save(update_fields=['storage_reserved', 'storage_used'])

                # Delete old chunks from storage
                for oc in old_file.chunks.all():
                    try:
                        engine.delete_chunk(oc.telegram_message_id)
                    except Exception:
                        pass
                old_file.chunks.all().delete()

                # Update existing FileItem
                old_file.name = session.filename
                old_file.size = session.total_size
                old_file.mime_type = session.mime_type
                old_file.sha256 = session.expected_sha256
                old_file.save()
                file_item = old_file
            else:
                # Atomically adjust quota
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
                    sha256=session.expected_sha256
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
            user = request.user
            user.refresh_from_db()
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
    permission_classes = [permissions.AllowAny]

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

        engine = get_storage_engine()
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
    permission_classes = [permissions.IsAuthenticated]
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
    permission_classes = [permissions.IsAuthenticated]
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
    permission_classes = [permissions.AllowAny]

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
