import io
import math
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from config.env_schema import AppConfig
from drive.models import Folder, FileItem, UploadSession, UploadChunk, Permission, ShareLink
from drive.permissions import validate_folder_move, resolve_effective_role, can_delete_forever
from storage_engine.signed_token import generate_media_token, verify_media_token

User = get_user_model()


class ConfigAndSecurityTests(TestCase):
    def test_jwt_secret_validation_rejects_short_key(self):
        with self.assertRaises(ValueError):
            AppConfig(JWT_SECRET_KEY="too-short")

    def test_jwt_secret_validation_accepts_valid_key(self):
        valid_key = "a" * 32
        cfg = AppConfig(JWT_SECRET_KEY=valid_key)
        self.assertEqual(cfg.JWT_SECRET_KEY, valid_key)

    def test_chunk_size_env_validation(self):
        valid_key = "a" * 32
        # 1. Min below 1 MB is rejected (Telegram hard floor)
        with self.assertRaises(ValueError):
            AppConfig(JWT_SECRET_KEY=valid_key, MIN_CHUNK_SIZE_MB=0)

        # 2. Max above 2000 MB is rejected (Telegram hard ceiling)
        with self.assertRaises(ValueError):
            AppConfig(JWT_SECRET_KEY=valid_key, MAX_CHUNK_SIZE_MB=2500)

        # 3. Min greater than Max is rejected
        with self.assertRaises(ValueError):
            AppConfig(JWT_SECRET_KEY=valid_key, MIN_CHUNK_SIZE_MB=64, MAX_CHUNK_SIZE_MB=32)

        # 4. Default outside Min..Max is rejected
        with self.assertRaises(ValueError):
            AppConfig(JWT_SECRET_KEY=valid_key, MIN_CHUNK_SIZE_MB=8, MAX_CHUNK_SIZE_MB=32, DEFAULT_CHUNK_SIZE_MB=4)

        # 5. Valid custom chunk sizes accept
        cfg = AppConfig(JWT_SECRET_KEY=valid_key, MIN_CHUNK_SIZE_MB=8, DEFAULT_CHUNK_SIZE_MB=16, MAX_CHUNK_SIZE_MB=64)
        self.assertEqual(cfg.DEFAULT_CHUNK_SIZE_MB, 16)


class DrivePermissionAndSubfolderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_owner = User.objects.create_user(email="owner@test.com", password="password123")
        self.user_editor = User.objects.create_user(email="editor@test.com", password="password123")
        self.user_viewer = User.objects.create_user(email="viewer@test.com", password="password123")
        self.user_stranger = User.objects.create_user(email="stranger@test.com", password="password123")

        self.root_folder = Folder.objects.create(name="Root", owner=self.user_owner)
        self.sub_folder = Folder.objects.create(name="Sub", owner=self.user_owner, parent=self.root_folder)
        self.child_file = FileItem.objects.create(
            name="child.txt",
            folder=self.sub_folder,
            owner=self.user_owner,
            size=1024,
            mime_type="text/plain"
        )
        self.client.force_authenticate(user=self.user_owner)

    def test_subfolder_detail_operations_not_404(self):
        """
        Verify Bug 1 fix: Detail operations on subfolders and files inside subfolders
        MUST NOT return 404 even when called without query parameters!
        """
        # 1. Retrieve subfolder detail
        folder_res = self.client.get(f'/api/drive/folders/{self.sub_folder.id}/')
        self.assertEqual(folder_res.status_code, status.HTTP_200_OK)
        self.assertEqual(folder_res.data['name'], 'Sub')

        # 2. Rename file inside subfolder
        rename_res = self.client.post(f'/api/drive/files/{self.child_file.id}/rename/', {'name': 'renamed.txt'})
        self.assertEqual(rename_res.status_code, status.HTTP_200_OK)
        self.assertEqual(rename_res.data['name'], 'renamed.txt')

        # 3. Trash file inside subfolder
        trash_res = self.client.post(f'/api/drive/files/{self.child_file.id}/trash/')
        self.assertEqual(trash_res.status_code, status.HTTP_200_OK)

        # 4. Restore file inside subfolder
        restore_res = self.client.post(f'/api/drive/files/{self.child_file.id}/restore/')
        self.assertEqual(restore_res.status_code, status.HTTP_200_OK)

    def test_ancestor_folder_owner_does_not_usurp_file_ownership(self):
        another_file = FileItem.objects.create(
            name="another.txt",
            folder=self.sub_folder,
            owner=self.user_editor,
            size=1024
        )
        role = resolve_effective_role(self.user_owner, another_file)
        self.assertEqual(role, 'editor')
        self.assertFalse(can_delete_forever(self.user_owner, another_file))
        self.assertTrue(can_delete_forever(self.user_editor, another_file))

    def test_permission_inheritance_from_parent_folder(self):
        Permission.objects.create(user=self.user_viewer, folder=self.root_folder, role='viewer')
        sub_role = resolve_effective_role(self.user_viewer, self.sub_folder)
        self.assertEqual(sub_role, 'viewer')

        file_role = resolve_effective_role(self.user_viewer, self.child_file)
        self.assertEqual(file_role, 'viewer')

        stranger_role = resolve_effective_role(self.user_stranger, self.child_file)
        self.assertIsNone(stranger_role)

    def test_cyclic_folder_move_prevention(self):
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_folder_move(self.root_folder, self.root_folder)

        with self.assertRaises(ValidationError):
            validate_folder_move(self.root_folder, self.sub_folder)


class UploadAndStreamingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="uploader@test.com",
            password="password123",
            storage_quota=5000  # 5,000 bytes limit
        )
        self.client.force_authenticate(user=self.user)

    def test_quota_exhaustion_rejects_upload(self):
        # Attempting to upload 10,000 bytes when quota is 5,000 bytes
        res = self.client.post('/api/drive/uploads/initiate/', {
            'filename': 'huge_file.zip',
            'total_size': 10000,
            'mime_type': 'application/zip'
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Insufficient storage quota', str(res.data))

    def test_upload_cancel_releases_reserved_quota(self):
        # 1. Initiate 2,000 bytes upload
        init_res = self.client.post('/api/drive/uploads/initiate/', {
            'filename': 'test_cancel.dat',
            'total_size': 2000,
            'mime_type': 'application/octet-stream'
        })
        self.assertEqual(init_res.status_code, status.HTTP_201_CREATED)
        session_id = init_res.data['session_id']

        self.user.refresh_from_db()
        self.assertEqual(self.user.storage_reserved, 2000)

        # 2. Cancel upload session
        cancel_res = self.client.post(f'/api/drive/uploads/{session_id}/cancel/')
        self.assertEqual(cancel_res.status_code, status.HTTP_200_OK)

        # Reserved quota must be restored to 0
        self.user.refresh_from_db()
        self.assertEqual(self.user.storage_reserved, 0)

    def test_filename_sanitization_removes_path_traversal(self):
        res = self.client.post('/api/drive/uploads/initiate/', {
            'filename': '../../../../etc/passwd',
            'total_size': 500,
            'mime_type': 'text/plain'
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        session = UploadSession.objects.get(pk=res.data['session_id'])
        self.assertNotIn('/', session.filename)
        self.assertNotIn('\\', session.filename)

    def test_range_streaming_rfc9110_and_416_edge_cases(self):
        test_payload = b"0123456789ABCDEF" * 20  # 320 bytes
        total_size = len(test_payload)

        # Create session and complete
        init_res = self.client.post('/api/drive/uploads/initiate/', {
            'filename': 'stream_test.txt',
            'total_size': total_size,
            'mime_type': 'text/plain'
        })
        session_id = init_res.data['session_id']
        self.client.put(f'/api/drive/uploads/{session_id}/chunks/0/', data=test_payload, content_type='application/octet-stream')
        comp_res = self.client.post(f'/api/drive/uploads/{session_id}/complete/')
        file_id = comp_res.data['id']

        # 1. Valid range bytes=0-15
        res_206 = self.client.get(f'/api/drive/files/{file_id}/stream/', HTTP_RANGE='bytes=0-15')
        self.assertEqual(res_206.status_code, 206)
        content = b''.join(res_206.streaming_content)
        self.assertEqual(content, test_payload[:16])

        # 2. Invalid range beyond file size -> 416
        res_416 = self.client.get(f'/api/drive/files/{file_id}/stream/', HTTP_RANGE=f'bytes={total_size + 100}-')
        self.assertEqual(res_416.status_code, 416)
        self.assertEqual(res_416['Content-Range'], f'bytes */{total_size}')

        # 3. Full stream without Range header (HTTP 200, Content-Length exact match)
        res_200 = self.client.get(f'/api/drive/files/{file_id}/stream/')
        self.assertEqual(res_200.status_code, 200)
        self.assertEqual(int(res_200['Content-Length']), total_size)
        content_200 = b''.join(res_200.streaming_content)
        self.assertEqual(content_200, test_payload)

    def test_chunk_size_optimization_and_telegram_policy_guardrails(self):
        self.user.storage_quota = None  # Unlimited quota for this test
        self.user.save()

        # 1. Unspecified chunk_size defaults to DEFAULT_CHUNK_SIZE_MB (8 MB)
        res_default = self.client.post('/api/drive/uploads/initiate/', {
            'filename': 'default_chunk.dat',
            'total_size': 20 * 1024 * 1024,
        })
        self.assertEqual(res_default.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_default.data['chunk_size'], 8 * 1024 * 1024)
        self.assertEqual(res_default.data['total_chunks'], 3)

        # 2. Custom valid chunk_size (16 MB)
        res_custom = self.client.post('/api/drive/uploads/initiate/', {
            'filename': 'custom_chunk.dat',
            'total_size': 32 * 1024 * 1024,
            'chunk_size': 16 * 1024 * 1024,
        })
        self.assertEqual(res_custom.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_custom.data['chunk_size'], 16 * 1024 * 1024)
        self.assertEqual(res_custom.data['total_chunks'], 2)

        # 3. Chunk size below minimum is clamped to MIN_CHUNK_SIZE_MB (4 MB)
        res_low = self.client.post('/api/drive/uploads/initiate/', {
            'filename': 'low_chunk.dat',
            'total_size': 10 * 1024 * 1024,
            'chunk_size': 512 * 1024,  # 512 KB requested
        })
        self.assertEqual(res_low.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_low.data['chunk_size'], 4 * 1024 * 1024)

        # 4. Chunk size above server max is clamped to MAX_CHUNK_SIZE_MB (32 MB)
        res_high = self.client.post('/api/drive/uploads/initiate/', {
            'filename': 'high_chunk.dat',
            'total_size': 100 * 1024 * 1024,
            'chunk_size': 100 * 1024 * 1024,  # 100 MB requested
        })
        self.assertEqual(res_high.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_high.data['chunk_size'], 32 * 1024 * 1024)

        # 5. Non-aligned chunk size is aligned to 1024 bytes (1 KB boundary)
        res_unaligned = self.client.post('/api/drive/uploads/initiate/', {
            'filename': 'unaligned.dat',
            'total_size': 10 * 1024 * 1024,
            'chunk_size': (8 * 1024 * 1024) + 777,
        })
        self.assertEqual(res_unaligned.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_unaligned.data['chunk_size'] % 1024, 0)
        self.assertEqual(res_unaligned.data['chunk_size'], 8 * 1024 * 1024)

    def test_public_share_link_access(self):
        # Create file and share link
        file_item = FileItem.objects.create(name="shared.txt", owner=self.user, size=100)
        share_res = self.client.post('/api/drive/shares/', {'file': file_item.id, 'role': 'viewer'})
        self.assertEqual(share_res.status_code, status.HTTP_201_CREATED)
        token = share_res.data['token']

        # Unauthenticated client accesses public share link
        unauth_client = APIClient()
        pub_res = unauth_client.get(f'/api/drive/shares/public/{token}/')
        self.assertEqual(pub_res.status_code, status.HTTP_200_OK)
        self.assertEqual(pub_res.data['file']['name'], 'shared.txt')
        self.assertIn('media_token', pub_res.data)

    def test_password_protected_share_link(self):
        file_item = FileItem.objects.create(name="secret.pdf", owner=self.user, size=200)
        share_res = self.client.post('/api/drive/shares/', {
            'file': file_item.id,
            'role': 'viewer',
            'password': 'Password123'
        })
        token = share_res.data['token']

        unauth_client = APIClient()
        # 1. Access without password -> 403
        denied_res = unauth_client.get(f'/api/drive/shares/public/{token}/')
        self.assertEqual(denied_res.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Access with wrong password -> 403
        wrong_res = unauth_client.get(f'/api/drive/shares/public/{token}/?password=wrong')
        self.assertEqual(wrong_res.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Access with correct password -> 200
        ok_res = unauth_client.get(f'/api/drive/shares/public/{token}/?password=Password123')
        self.assertEqual(ok_res.status_code, status.HTTP_200_OK)
        self.assertEqual(ok_res.data['file']['name'], 'secret.pdf')

    def test_expired_share_link_returns_404(self):
        from datetime import timedelta
        from django.utils import timezone
        file_item = FileItem.objects.create(name="expired.pdf", owner=self.user, size=200)
        share = ShareLink.objects.create(
            token="expired_token_123",
            file=file_item,
            expires_at=timezone.now() - timedelta(days=1)
        )
        unauth_client = APIClient()
        res = unauth_client.get(f'/api/drive/shares/public/{share.token}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_acl_viewer_cannot_rename_or_trash(self):
        viewer = User.objects.create_user(email="viewer2@test.com", password="password123")
        file_item = FileItem.objects.create(name="protected.txt", owner=self.user, size=100)
        Permission.objects.create(user=viewer, file=file_item, role='viewer')

        viewer_client = APIClient()
        viewer_client.force_authenticate(user=viewer)

        # Viewer renaming -> 403
        rename_res = viewer_client.post(f'/api/drive/files/{file_item.id}/rename/', {'name': 'hacked.txt'})
        self.assertEqual(rename_res.status_code, status.HTTP_403_FORBIDDEN)

        # Viewer trashing -> 403
        trash_res = viewer_client.post(f'/api/drive/files/{file_item.id}/trash/')
        self.assertEqual(trash_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_owner_cannot_delete_forever(self):
        editor = User.objects.create_user(email="editor2@test.com", password="password123")
        file_item = FileItem.objects.create(name="precious.txt", owner=self.user, size=100)
        Permission.objects.create(user=editor, file=file_item, role='editor')

        editor_client = APIClient()
        editor_client.force_authenticate(user=editor)

        # Editor permanent delete -> 403 Forbidden!
        delete_res = editor_client.delete(f'/api/drive/files/{file_item.id}/')
        self.assertEqual(delete_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_delete_forever_restores_quota(self):
        self.user.storage_used = 1500
        self.user.save()
        file_item = FileItem.objects.create(name="delete_me.dat", owner=self.user, size=500)

        del_res = self.client.delete(f'/api/drive/files/{file_item.id}/')
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertEqual(self.user.storage_used, 1000)
        self.assertFalse(FileItem.objects.filter(pk=file_item.id).exists())

    def test_toggle_star_on_file_and_folder(self):
        folder = Folder.objects.create(name="StarredFolder", owner=self.user)
        file_item = FileItem.objects.create(name="StarredFile.txt", owner=self.user, size=50)

        # Star folder
        star_folder_res = self.client.post(f'/api/drive/folders/{folder.id}/toggle_star/')
        self.assertTrue(star_folder_res.data['is_starred'])

        # Unstar folder
        unstar_folder_res = self.client.post(f'/api/drive/folders/{folder.id}/toggle_star/')
        self.assertFalse(unstar_folder_res.data['is_starred'])

        # Star file
        star_file_res = self.client.post(f'/api/drive/files/{file_item.id}/toggle_star/')
        self.assertTrue(star_file_res.data['is_starred'])

    def test_upload_session_retrieve_for_resumable_upload(self):
        init_res = self.client.post('/api/drive/uploads/initiate/', {
            'filename': 'resumable.dat',
            'total_size': 1000,
            'mime_type': 'application/octet-stream'
        })
        session_id = init_res.data['session_id']

        get_res = self.client.get(f'/api/drive/uploads/{session_id}/')
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertEqual(get_res.data['session_id'], session_id)
        self.assertEqual(get_res.data['uploaded_chunks'], [])
        self.assertEqual(get_res.data['status'], 'UPLOADING')


