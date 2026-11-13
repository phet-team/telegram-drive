from django.urls import path

from storage_engine import views

urlpatterns = [
    path('health/storage/', views.StorageHealthView.as_view(), name='storage_health'),
    path('admin/storage/', views.StorageSettingsView.as_view(), name='storage_settings'),
    path('admin/storage/test/', views.StorageTestView.as_view(), name='storage_test'),
    path('admin/storage/test-alert/', views.StorageTestAlertView.as_view(), name='storage_test_alert'),
    path('admin/storage/selftest/', views.StorageSelftestView.as_view(), name='storage_selftest'),
    path('admin/storage/login/start/', views.StorageLoginStartView.as_view(), name='storage_login_start'),
    path('admin/storage/login/verify/', views.StorageLoginVerifyView.as_view(), name='storage_login_verify'),
    path('admin/storage/login/password/', views.StorageLoginPasswordView.as_view(), name='storage_login_password'),
    path('admin/storage/login/cancel/', views.StorageLoginCancelView.as_view(), name='storage_login_cancel'),

    # Per-user storage ("My storage")
    path('storage/me/', views.UserStorageMeView.as_view(), name='user_storage_me'),
    path('storage/me/login/start/', views.UserStorageLoginStartView.as_view(), name='user_storage_login_start'),
    path('storage/me/login/verify/', views.UserStorageLoginVerifyView.as_view(), name='user_storage_login_verify'),
    path('storage/me/login/password/', views.UserStorageLoginPasswordView.as_view(), name='user_storage_login_password'),
    path('storage/me/login/cancel/', views.UserStorageLoginCancelView.as_view(), name='user_storage_login_cancel'),
    path('storage/me/test/', views.UserStorageTestView.as_view(), name='user_storage_test'),
    path('storage/me/disconnect/', views.UserStorageDisconnectView.as_view(), name='user_storage_disconnect'),

    # User management (superuser)
    path('admin/users/', views.AdminUsersView.as_view(), name='admin_users'),
    path('admin/users/<int:pk>/', views.AdminUserDetailView.as_view(), name='admin_user_detail'),
]
