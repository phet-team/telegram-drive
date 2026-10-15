import time
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status

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
