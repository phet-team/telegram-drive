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
]
