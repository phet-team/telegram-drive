import time
from datetime import timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from authentication.models import ApiToken
from drive.models import Folder, FileItem

User = get_user_model()


class AuthenticationUnitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.register_url = '/api/auth/register/'
        self.login_url = '/api/auth/login/'
        self.refresh_url = '/api/auth/token/refresh/'
        self.logout_url = '/api/auth/logout/'
        self.telegram_url = '/api/auth/telegram/'

    def test_register_success(self):
        res = self.client.post(self.register_url, {
            'email': 'newuser@example.com',
            'name': 'New User',
            'password': 'SecurePassword123!'
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn('tokens', res.data)
        self.assertIn('access', res.data['tokens'])
        self.assertEqual(User.objects.filter(email='newuser@example.com').count(), 1)

    def test_register_duplicate_email_rejected(self):
        User.objects.create_user(email='existing@example.com', password='password123')
        res = self.client.post(self.register_url, {
            'email': 'existing@example.com',
            'password': 'AnotherPassword123'
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_short_password_rejected(self):
        res = self.client.post(self.register_url, {
            'email': 'shortpass@example.com',
            'password': 'short'
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_success_and_token_structure(self):
        User.objects.create_user(email='loginuser@example.com', password='Password123!')
        res = self.client.post(self.login_url, {
            'email': 'loginuser@example.com',
            'password': 'Password123!'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('access', res.data)
        # Verify HttpOnly Secure SameSite Cookie is set
        self.assertIn('refresh_token', res.cookies)
        self.assertTrue(res.cookies['refresh_token']['httponly'])
        self.assertEqual(res.cookies['refresh_token']['samesite'], 'Lax')
        self.assertEqual(res.cookies['refresh_token']['path'], '/api/auth/')

    def test_login_invalid_password_rejected(self):
        User.objects.create_user(email='loginfail@example.com', password='Password123!')
        res = self.client.post(self.login_url, {
            'email': 'loginfail@example.com',
            'password': 'WrongPassword999'
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_token_refresh_via_httponly_cookie(self):
        user = User.objects.create_user(email='refreshtest@example.com', password='Password123!')
        login_res = self.client.post(self.login_url, {'email': user.email, 'password': 'Password123!'})
        refresh_cookie = login_res.cookies['refresh_token'].value

        # Client automatically provides cookie
        self.client.cookies['refresh_token'] = refresh_cookie
        ref_res = self.client.post(self.refresh_url)
        self.assertEqual(ref_res.status_code, status.HTTP_200_OK)
        self.assertIn('access', ref_res.data)
        # Verify rotated cookie is issued
        self.assertIn('refresh_token', ref_res.cookies)
        new_refresh_cookie = ref_res.cookies['refresh_token'].value
        self.assertNotEqual(refresh_cookie, new_refresh_cookie)

    def test_logout_destroys_cookie_and_blacklists_token(self):
        user = User.objects.create_user(email='logouttest@example.com', password='Password123!')
        login_res = self.client.post(self.login_url, {'email': user.email, 'password': 'Password123!'})
        refresh_cookie = login_res.cookies['refresh_token'].value

        self.client.cookies['refresh_token'] = refresh_cookie
        logout_res = self.client.post(self.logout_url)
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)
        # Verify cookie is cleared (Max-Age=0)
        self.assertEqual(logout_res.cookies['refresh_token']['max-age'], 0)

        # Trying to refresh with the blacklisted cookie must be rejected with 401
        self.client.cookies['refresh_token'] = refresh_cookie
        second_ref_res = self.client.post(self.refresh_url)
        self.assertEqual(second_ref_res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_telegram_auth_replay_attack_rejected(self):
        # auth_date older than 24 hours
        expired_auth_date = int(time.time()) - 90000
        res = self.client.post(self.telegram_url, {
            'id': 12345678,
            'first_name': 'Test',
            'auth_date': expired_auth_date,
            'hash': 'invalid_hash_value'
        })
        self.assertIn(res.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_503_SERVICE_UNAVAILABLE])

    def test_rate_limiting_throttle_protection(self):
        """Verifies WAF rate limiting triggers 429 on rapid brute force attempts"""
        for _ in range(5):
            self.client.post(self.login_url, {'email': 'brute@test.com', 'password': 'pass'})
        
        # 6th attempt within the same minute MUST trigger HTTP 429 Too Many Requests
        blocked_res = self.client.post(self.login_url, {'email': 'brute@test.com', 'password': 'pass'})
        self.assertEqual(blocked_res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


def make_token(user, scopes, folder=None):
    """Helper: creates an ApiToken directly and returns (token, plaintext)."""
    plaintext = ApiToken.generate_plaintext()
    token = ApiToken.objects.create(
        user=user,
        name='test-token',
        prefix=plaintext[:12],
        token_hash=ApiToken.hash_token(plaintext),
        scopes=scopes,
        folder=folder,
    )
    return token, plaintext


class ApiTokenManagementTests(TestCase):
    """Plan item 1 + 7: create/revoke/list behaviour and the 20-token limit."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(email='tokenuser@example.com', password='Password123!')
        self.other = User.objects.create_user(email='tokenother@example.com', password='Password123!')
        self.tokens_url = '/api/auth/tokens/'
        self.client.force_authenticate(user=self.user)

    def test_create_returns_plaintext_once_and_db_holds_only_hash(self):
        res = self.client.post(self.tokens_url, {'name': 'studio', 'scopes': ['read', 'files:upload']})
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        plaintext = res.data['token']
        self.assertTrue(plaintext.startswith('tdk_'))

        # DB holds only the hash, never the plaintext
        obj = ApiToken.objects.get(pk=res.data['id'])
        self.assertEqual(obj.token_hash, ApiToken.hash_token(plaintext))
        self.assertNotEqual(obj.token_hash, plaintext)
        self.assertFalse(ApiToken.objects.filter(token_hash=plaintext).exists())

        # list never returns the plaintext
        listing = self.client.get(self.tokens_url)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.data), 1)
        for row in listing.data:
            self.assertNotIn('token', row)
            self.assertEqual(row['prefix'], plaintext[:12])

    def test_create_with_invalid_scope_rejected(self):
        res = self.client.post(self.tokens_url, {'name': 'x', 'scopes': ['read', 'files:delete']})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_with_empty_scopes_rejected(self):
        res = self.client.post(self.tokens_url, {'name': 'x', 'scopes': []})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_with_folder_must_be_writable(self):
        folder = Folder.objects.create(name='gen-image', owner=self.user)
        res = self.client.post(self.tokens_url, {
            'name': 'studio', 'scopes': ['read'], 'folder_id': str(folder.id),
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['folder']['id'], str(folder.id))

        # other user's folder → 400
        other_folder = Folder.objects.create(name='not-mine', owner=self.other)
        res2 = self.client.post(self.tokens_url, {
            'name': 'studio2', 'scopes': ['read'], 'folder_id': str(other_folder.id),
        })
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_revoke_sets_revoked_at_and_is_idempotent(self):
        res = self.client.post(self.tokens_url, {'name': 'x', 'scopes': ['read']})
        tid = res.data['id']

        first = self.client.delete(f'{self.tokens_url}{tid}/')
        self.assertEqual(first.status_code, status.HTTP_204_NO_CONTENT)
        obj = ApiToken.objects.get(pk=tid)
        self.assertIsNotNone(obj.revoked_at)

        # already revoked → still 204
        second = self.client.delete(f'{self.tokens_url}{tid}/')
        self.assertEqual(second.status_code, status.HTTP_204_NO_CONTENT)

    def test_cannot_revoke_someone_elses_token(self):
        res = self.client.post(self.tokens_url, {'name': 'x', 'scopes': ['read']})
        tid = res.data['id']
        self.client.force_authenticate(user=self.other)
        res = self.client.delete(f'{self.tokens_url}{tid}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_21st_active_token_rejected(self):
        for i in range(ApiToken.MAX_ACTIVE_TOKENS):
            res = self.client.post(self.tokens_url, {'name': f'tok-{i}', 'scopes': ['read']})
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        beyond = self.client.post(self.tokens_url, {'name': 'tok-21', 'scopes': ['read']})
        self.assertEqual(beyond.status_code, status.HTTP_400_BAD_REQUEST)


class ApiTokenAuthenticationTests(TestCase):
    """Plan item 2: valid / revoked / unknown / inactive-user tokens."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(email='authuser@example.com', password='Password123!')
        self.token, self.plaintext = make_token(self.user, ['read', 'folders:create', 'files:upload'])
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.plaintext}')

    def test_valid_token_authenticates_and_sets_auth(self):
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['email'], self.user.email)

    def test_revoked_token_gets_401_with_message(self):
        ApiToken.objects.filter(pk=self.token.pk).update(revoked_at=timezone.now())
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('revoked', str(res.data['detail']).lower())

    def test_unknown_token_gets_401_with_message(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer tdk_totallyunknownvalue')
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('invalid', str(res.data['detail']).lower())

    def test_inactive_user_gets_401_with_message(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('inactive', str(res.data['detail']).lower())

    def test_jwt_still_works_alongside_token_auth(self):
        """Plan item 3: JWT login flow unchanged by the new auth class."""
        login = self.client.post('/api/auth/login/', {
            'email': self.user.email, 'password': 'Password123!',
        })
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')
        me = self.client.get('/api/auth/me/')
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data['email'], self.user.email)

    def test_last_used_updated_at_most_once_per_60s(self):
        now = timezone.now()
        # recent write → must NOT be updated again
        ApiToken.objects.filter(pk=self.token.pk).update(last_used_at=now)
        self.client.get('/api/auth/me/')
        self.token.refresh_from_db()
        self.assertEqual(self.token.last_used_at, now)

        # older than the 60 s window → written
        stale = now - timedelta(seconds=61)
        ApiToken.objects.filter(pk=self.token.pk).update(last_used_at=stale)
        self.client.get('/api/auth/me/')
        self.token.refresh_from_db()
        self.assertNotEqual(self.token.last_used_at, stale)
        self.assertGreater(self.token.last_used_at, stale)


class ApiTokenScopeTests(TestCase):
    """Plan item 4: each scope allows exactly its rows; everything else is 403."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(email='scopeuser@example.com', password='Password123!')
        self.folder = Folder.objects.create(name='scope-root', owner=self.user)
        FileItem.objects.create(
            name='note.txt', folder=self.folder, owner=self.user, size=10, mime_type='text/plain',
        )

    def _auth(self, scopes, folder=None):
        token, plaintext = make_token(self.user, scopes, folder=folder)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {plaintext}')
        return client

    def test_read_scope_allows_lists_and_detail_only(self):
        client = self._auth(['read'])
        self.assertEqual(client.get('/api/auth/me/').status_code, status.HTTP_200_OK)
        self.assertEqual(client.get('/api/drive/folders/').status_code, status.HTTP_200_OK)
        self.assertEqual(client.get(f'/api/drive/folders/{self.folder.id}/').status_code, status.HTTP_200_OK)
        self.assertEqual(client.get('/api/drive/files/?folder=' + str(self.folder.id)).status_code, status.HTTP_200_OK)

    def test_read_scope_cannot_create_folders(self):
        client = self._auth(['read'])
        res = client.post('/api/drive/folders/', {'name': 'new-folder', 'parent': str(self.folder.id)})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_scope_allows_folder_create(self):
        client = self._auth(['folders:create'])
        res = client.post('/api/drive/folders/', {'name': 'made-by-token', 'parent': str(self.folder.id)})
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_without_upload_scope_initiate_is_403(self):
        client = self._auth(['read'])
        res = client.post('/api/drive/uploads/initiate/', {
            'filename': 'img.png', 'total_size': 1024, 'folder_id': str(self.folder.id),
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_upload_scope_allows_initiate(self):
        client = self._auth(['files:upload'])
        res = client.post('/api/drive/uploads/initiate/', {
            'filename': 'img.png', 'total_size': 1024, 'folder_id': str(self.folder.id),
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_share_and_permission_endpoints_are_403_for_tokens(self):
        client = self._auth(['read', 'folders:create', 'files:upload'])
        self.assertEqual(client.get('/api/drive/shares/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(client.get('/api/drive/permissions/').status_code, status.HTTP_403_FORBIDDEN)
        res = client.post('/api/drive/shares/', {'folder': str(self.folder.id), 'role': 'viewer'})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_token_management_routes_are_403_for_tokens(self):
        client = self._auth(['read'])
        self.assertEqual(client.get('/api/auth/tokens/').status_code, status.HTTP_403_FORBIDDEN)
        res = client.post('/api/auth/tokens/', {'name': 'x', 'scopes': ['read']})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_trash_and_delete_are_403_for_tokens(self):
        client = self._auth(['read', 'folders:create', 'files:upload'])
        res = client.post(f'/api/drive/folders/{self.folder.id}/trash/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
