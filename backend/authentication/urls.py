from django.urls import path
from authentication.views import (
    RegisterView, LoginView, MeView, LogoutView,
    TelegramAuthView, GoogleAuthView, CookieTokenRefreshView
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('login/', LoginView.as_view(), name='auth_login'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('me/', MeView.as_view(), name='auth_me'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
    path('telegram/', TelegramAuthView.as_view(), name='auth_telegram'),
    path('google/', GoogleAuthView.as_view(), name='auth_google'),
]
