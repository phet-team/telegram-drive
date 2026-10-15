from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drive.views import (
    FolderViewSet, FileItemViewSet, UploadViewSet, ShareViewSet,
    PermissionViewSet, FileStreamView, PublicShareView
)

router = DefaultRouter()
router.register(r'folders', FolderViewSet, basename='folder')
router.register(r'files', FileItemViewSet, basename='file')
router.register(r'uploads', UploadViewSet, basename='upload')
router.register(r'shares', ShareViewSet, basename='share')
router.register(r'permissions', PermissionViewSet, basename='permission')

urlpatterns = [
    path('shares/public/<str:token>/', PublicShareView.as_view(), name='public_share'),
    path('files/<uuid:pk>/stream/', FileStreamView.as_view(), name='file_stream'),
    path('', include(router.urls)),
]
