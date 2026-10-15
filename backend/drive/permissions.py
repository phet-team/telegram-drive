from typing import Optional
from django.db.models import Q
from rest_framework.exceptions import ValidationError, PermissionDenied
from drive.models import Folder, FileItem, Permission

ROLE_WEIGHTS = {
    'none': 0,
    'viewer': 2,
    'editor': 3,
    'owner': 4
}


def role_to_weight(role: Optional[str]) -> int:
    return ROLE_WEIGHTS.get(role, 0)


def weight_to_role(weight: int) -> Optional[str]:
    for r, w in ROLE_WEIGHTS.items():
        if w == weight and r != 'none':
            return r
    return None


def resolve_effective_role(user, item) -> Optional[str]:
    """
    Computes effective permission for a user on a Folder or FileItem.
    Adheres strictly to:
    1. Direct file/folder owner gets 'owner'.
    2. Ancestor folder owner gets 'editor' on children (NOT owner - preserves ownership isolation).
    3. Effective role = max(Direct Role, Inherited Role).
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return None

    if user.is_superuser:
        return 'owner'

    # 1. Direct owner check
    if item.owner_id == user.id:
        return 'owner'

    is_folder = isinstance(item, Folder)
    
    # 2. Check direct permission on this item
    direct_perm = None
    if is_folder:
        direct_perm = Permission.objects.filter(folder=item, user=user).first()
    else:
        direct_perm = Permission.objects.filter(file=item, user=user).first()

    direct_weight = role_to_weight(direct_perm.role) if direct_perm else 0

    # 3. Traverse parent hierarchy for inherited permission
    inherited_weight = 0
    curr_folder = item.parent if is_folder else item.folder

    while curr_folder:
        if curr_folder.owner_id == user.id:
            # Ancestor folder owner gets at most 'editor' on descendants
            inherited_weight = max(inherited_weight, ROLE_WEIGHTS['editor'])
            break
        
        parent_perm = Permission.objects.filter(folder=curr_folder, user=user).first()
        if parent_perm:
            inherited_weight = max(inherited_weight, role_to_weight(parent_perm.role))
            
        curr_folder = curr_folder.parent

    max_weight = max(direct_weight, inherited_weight)
    return weight_to_role(max_weight)


# Action-level Authorization Matrix
def can_read(user, item) -> bool:
    role = resolve_effective_role(user, item)
    return role_to_weight(role) >= ROLE_WEIGHTS['viewer']


def can_write(user, item) -> bool:
    role = resolve_effective_role(user, item)
    return role_to_weight(role) >= ROLE_WEIGHTS['editor']


def can_delete_forever(user, item) -> bool:
    """Only true Owner can delete permanently"""
    return item.owner_id == user.id or user.is_superuser


def can_share(user, item) -> bool:
    role = resolve_effective_role(user, item)
    return role_to_weight(role) >= ROLE_WEIGHTS['editor']


def validate_folder_move(folder_to_move: Folder, target_folder: Optional[Folder]):
    """
    Prevents cyclic moves:
    - Cannot move folder into itself.
    - Cannot move folder into any of its own descendants.
    """
    if target_folder is None:
        return  # Moving to root is always acyclic

    if folder_to_move.id == target_folder.id:
        raise ValidationError("Cannot move folder into itself.")

    curr = target_folder
    while curr is not None:
        if curr.id == folder_to_move.id:
            raise ValidationError("Cannot move a folder into its own descendant.")
        curr = curr.parent


def is_item_or_ancestor_trashed(item) -> bool:
    """Checks if an item itself or any of its ancestor folders is marked as trashed."""
    if not item:
        return False
    if getattr(item, 'is_trashed', False):
        return True
    curr = getattr(item, 'parent', None) if isinstance(item, Folder) else getattr(item, 'folder', None)
    visited = set()
    while curr and curr.id not in visited:
        visited.add(curr.id)
        if curr.is_trashed:
            return True
        curr = curr.parent
    return False


def get_all_trashed_folder_ids() -> set:
    """Returns set of all folder IDs that are trashed or inside a trashed folder."""
    trashed_ids = set(Folder.objects.filter(is_trashed=True).values_list('id', flat=True))
    if not trashed_ids:
        return set()
    all_trashed = set(trashed_ids)
    frontier = list(trashed_ids)
    while frontier:
        sub = list(Folder.objects.filter(parent_id__in=frontier).values_list('id', flat=True))
        new_sub = [cid for cid in sub if cid not in all_trashed]
        if not new_sub:
            break
        all_trashed.update(new_sub)
        frontier = new_sub
    return all_trashed


def get_accessible_folders(user, parent_id=None, is_trashed=False, is_shared=False):
    """
    QuerySet filter for folders accessible by user.
    If parent_id == 'ALL': do not filter by parent hierarchy (used for detail actions).
    If parent_id is UUID/str: filter by specific parent.
    If parent_id is None: filter by root folders (parent__isnull=True).
    Inheritance: Users with permissions on an ancestor folder can access descendant folders.
    If is_shared is True: returns folders shared with this user by other users.
    """
    if not user or not user.is_authenticated:
        return Folder.objects.none()

    qs = Folder.objects.filter(is_trashed=is_trashed)

    if parent_id == 'ALL' and not is_trashed:
        trashed_ids = get_all_trashed_folder_ids()
        if trashed_ids:
            qs = qs.exclude(id__in=trashed_ids).exclude(parent_id__in=trashed_ids)

    # 1. Direct folders where user is owner or has direct permission
    direct_folder_ids = set(
        Folder.objects.filter(
            Q(owner=user) | Q(permissions__user=user)
        ).values_list('id', flat=True)
    )

    # 2. Descendant folders inherited from accessible ancestor folders
    accessible_folder_ids = set(direct_folder_ids)
    frontier = list(direct_folder_ids)
    while frontier:
        children_ids = list(Folder.objects.filter(parent_id__in=frontier).values_list('id', flat=True))
        new_children = [cid for cid in children_ids if cid not in accessible_folder_ids]
        if not new_children:
            break
        accessible_folder_ids.update(new_children)
        frontier = new_children

    if is_shared:
        if parent_id is None:
            # Root level of "Shared with me": only folders explicitly shared with user by someone else
            return qs.filter(permissions__user=user).exclude(owner=user).distinct()
        elif parent_id != 'ALL':
            qs = qs.filter(parent_id=parent_id)
    else:
        if parent_id != 'ALL':
            if parent_id is not None:
                qs = qs.filter(parent_id=parent_id)
            elif not is_trashed:
                # Root level of "My Drive": strictly only folders owned by this user
                return qs.filter(owner=user, parent__isnull=True)
            else:
                qs = qs.filter(owner=user)

    if user.is_superuser:
        return qs

    return qs.filter(id__in=accessible_folder_ids).distinct()


def get_accessible_files(user, folder_id=None, is_trashed=False, is_shared=False):
    """
    QuerySet filter for files accessible by user.
    If folder_id == 'ALL': do not filter by folder hierarchy (used for detail actions).
    If folder_id is UUID/str: filter by specific folder.
    If folder_id is None: filter by root files (folder__isnull=True).
    Inheritance: Users with access to a folder or any ancestor folder can access its files.
    If is_shared is True: returns files shared with this user by other users.
    """
    if not user or not user.is_authenticated:
        return FileItem.objects.none()

    qs = FileItem.objects.filter(is_trashed=is_trashed)

    if folder_id == 'ALL' and not is_trashed:
        trashed_ids = get_all_trashed_folder_ids()
        if trashed_ids:
            qs = qs.exclude(folder_id__in=trashed_ids)

    if is_shared:
        if folder_id is None:
            # Root level of "Shared with me": only files explicitly shared with user by someone else
            return qs.filter(permissions__user=user).exclude(owner=user).distinct()
        elif folder_id != 'ALL':
            qs = qs.filter(folder_id=folder_id)
    else:
        if folder_id != 'ALL':
            if folder_id is not None:
                qs = qs.filter(folder_id=folder_id)
            elif not is_trashed:
                # Root level of "My Drive": strictly only files owned by this user
                return qs.filter(owner=user, folder__isnull=True)
            else:
                qs = qs.filter(owner=user)

    if user.is_superuser:
        return qs

    direct_folder_ids = set(
        Folder.objects.filter(
            Q(owner=user) | Q(permissions__user=user)
        ).values_list('id', flat=True)
    )
    accessible_folder_ids = set(direct_folder_ids)
    frontier = list(direct_folder_ids)
    while frontier:
        children_ids = list(Folder.objects.filter(parent_id__in=frontier).values_list('id', flat=True))
        new_children = [cid for cid in children_ids if cid not in accessible_folder_ids]
        if not new_children:
            break
        accessible_folder_ids.update(new_children)
        frontier = new_children

    return qs.filter(
        Q(owner=user) |
        Q(permissions__user=user) |
        Q(folder_id__in=accessible_folder_ids)
    ).distinct()
