import time
from django.test import TestCase
from django.conf import settings
from storage_engine.client import (
    MockStorageEngine, TelegramMTProtoEngine,
    StorageEngineError, get_storage_engine
)
from storage_engine.signed_token import generate_media_token, verify_media_token


class StorageEngineUnitTests(TestCase):
    def setUp(self):
        self.mock_engine = MockStorageEngine()

    def test_mock_storage_upload_and_download(self):
        payload = b"Storage Engine Test Payload Data 123456789"
        msg_id, file_id = self.mock_engine.upload_chunk(payload, "test.dat")
        self.assertTrue(isinstance(msg_id, int))
        self.assertTrue(len(file_id) > 0)

        # Download and verify
        downloaded = self.mock_engine.download_chunk(file_id, msg_id)
        self.assertEqual(downloaded, payload)

    def test_mock_storage_nonexistent_chunk_raises_error(self):
        with self.assertRaises(StorageEngineError):
            self.mock_engine.download_chunk("non_existent_hash_12345")

    def test_mock_storage_delete_chunk(self):
        res = self.mock_engine.delete_chunk(123456)
        self.assertTrue(res)

    def test_mtproto_engine_defaults_to_saved_messages(self):
        engine = TelegramMTProtoEngine()
        # When TELEGRAM_STORAGE_CHAT_ID is empty, chat_id MUST be 'me' (Saved Messages)
        self.assertEqual(engine.chat_id, 'me')

    def test_signed_media_token_lifecycle(self):
        user_id = 42
        file_id = "550e8400-e29b-41d4-a716-446655440000"

        # 1. Valid token
        token = generate_media_token(user_id, file_id, expires_in_seconds=60)
        self.assertTrue(verify_media_token(user_id, file_id, token))

        # 2. Tampered file ID
        self.assertFalse(verify_media_token(user_id, "different-file-id", token))

        # 3. Tampered user ID
        self.assertFalse(verify_media_token(999, file_id, token))

        # 4. Expired token
        expired_token = generate_media_token(user_id, file_id, expires_in_seconds=-10)
        self.assertFalse(verify_media_token(user_id, file_id, expired_token))

        # 5. Malformed token
        self.assertFalse(verify_media_token(user_id, file_id, "malformed-token-string"))
