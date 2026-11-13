"""Resolve which storage account (system or per-user) backs a user's file operations."""

from drive.models import UserStorageAccount
from storage_engine.errors import StorageNotConnected

_CONNECT_MSG = "Connect your Telegram account in Settings → My storage to upload."


def resolve_upload_target(user) -> UserStorageAccount | None:
    """Return the user's UserStorageAccount, or None meaning the system storage engine."""
    if user.upload_target == 'system' and user.can_use_system_storage:
        return None
    account = getattr(user, 'storage_account', None)
    if account is not None and account.has_session:
        return account
    if user.can_use_system_storage:
        return None
    raise StorageNotConnected(_CONNECT_MSG)


def engine_for(account: UserStorageAccount | None):
    """Engine for a resolved account; None means the system-wide engine."""
    if account is None:
        from storage_engine.client import get_storage_engine
        return get_storage_engine()
    if not account.session_string_enc:
        from storage_engine.errors import StorageUnavailable
        raise StorageUnavailable('storage_not_connected')
    from storage_engine.client import get_storage_engine
    return get_storage_engine(account=account)


def engine_for_file(file_item):
    return engine_for(file_item.storage_account)
