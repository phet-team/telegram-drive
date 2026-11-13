from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from storage_engine.errors import ContentUnavailable, StorageNotConnected, StorageUnavailable


def storage_exception_handler(exc, context):
    """503 for StorageUnavailable, 410 for ContentUnavailable; everything else keeps DRF's handling."""
    if isinstance(exc, StorageUnavailable):
        response = Response(
            {'error': 'storage_unavailable', 'reason': exc.reason, 'message': exc.message},
            status=503,
        )
        response['Retry-After'] = str(exc.retry_after)
        return response
    if isinstance(exc, ContentUnavailable):
        return Response({'error': 'content_unavailable'}, status=410)
    if isinstance(exc, StorageNotConnected):
        return Response({'error': 'storage_not_connected', 'message': exc.message}, status=409)
    return drf_exception_handler(exc, context)
