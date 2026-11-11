from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied

from authentication.models import ApiToken

MAX_SUBTREE_DEPTH = 200


def get_api_token(request):
    """Returns the ApiToken authenticating this request, or None (JWT/user/PUBLIC)."""
    return request.auth if isinstance(request.auth, ApiToken) else None


def is_in_subtree(item_or_folder, root_folder) -> bool:
    """
    True if `item_or_folder` is `root_folder` itself or inside its descendant tree.
    Accepts a Folder or a FileItem (walks up through its folder). Depth-guarded.
    """
    if root_folder is None:
        return True
    if item_or_folder is None:
        return False

    folder = item_or_folder
    if hasattr(folder, 'folder_id') and not hasattr(folder, 'parent_id'):
        # It is a FileItem, not a Folder
        folder = folder.folder

    depth = 0
    visited = set()
    while folder is not None and depth < MAX_SUBTREE_DEPTH:
        if folder.id in visited:
            break
        if folder.id == root_folder.id:
            return True
        visited.add(folder.id)
        depth += 1
        folder = folder.parent
    return False


def enforce_token_subtree(request, item_or_folder, message="API token cannot access items outside its folder."):
    """
    Raises PermissionDenied when a folder-restricted API token targets an object
    outside the token's folder subtree. No-op for JWT / non-folder-restricted tokens.
    """
    token = get_api_token(request)
    if token is None or token.folder_id is None:
        return
    if not is_in_subtree(item_or_folder, token.folder):
        raise PermissionDenied(message)


class ApiTokenScopePermission(BasePermission):
    """
    Allow-list for API tokens. When `request.auth` is an ApiToken, only the
    (view, action, method) combinations mapped to one of the token's scopes
    are allowed; everything else is 403. Requests not authenticated by an
    API token (JWT users, anonymous, share links) pass through untouched.

    Views are matched by dotted module + class name so this module never
    imports the view modules (which would create import cycles).
    """
    message = "API token cannot use this endpoint"

    # (module_path, class_name, action, method) -> scopes that permit it
    SCOPE_RULES = {
        ApiToken.SCOPE_READ: {
            ('authentication.views', 'MeView', 'get', 'GET'),
            ('drive.views', 'FolderViewSet', 'list', 'GET'),
            ('drive.views', 'FolderViewSet', 'retrieve', 'GET'),
            ('drive.views', 'FileItemViewSet', 'list', 'GET'),
            ('drive.views', 'FileItemViewSet', 'retrieve', 'GET'),
        },
        ApiToken.SCOPE_FOLDERS_CREATE: {
            ('drive.views', 'FolderViewSet', 'create', 'POST'),
        },
        ApiToken.SCOPE_FILES_UPLOAD: {
            ('drive.views', 'UploadViewSet', 'initiate', 'POST'),
            ('drive.views', 'UploadViewSet', 'upload_chunk', 'PUT'),
            ('drive.views', 'UploadViewSet', 'complete', 'POST'),
            ('drive.views', 'UploadViewSet', 'retrieve', 'GET'),
        },
    }

    _REVERSE = {}
    for _scope, _rules in SCOPE_RULES.items():
        for _rule in _rules:
            _REVERSE.setdefault(_rule, set()).add(_scope)

    def has_permission(self, request, view):
        token = get_api_token(request)
        if token is None:
            return True

        method = request.method.upper()
        action = getattr(view, 'action', None) or method.lower()
        rule = (view.__module__, view.__class__.__name__, action, method)
        allowed_scopes = self._REVERSE.get(rule, set())
        return bool(allowed_scopes and (allowed_scopes & set(token.scopes)))
