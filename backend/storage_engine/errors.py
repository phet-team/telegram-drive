class StorageEngineError(Exception):
    """Unexpected storage failure. Surfaces as HTTP 500 (traceback is logged)."""


class ContentUnavailable(StorageEngineError):
    """The stored content cannot be found (e.g. the Telegram message was deleted). HTTP 410."""


# One English sentence per reason, shown in API responses and alerts.
REASON_MESSAGES = {
    'telegram_session_expired': 'The Telegram session is no longer valid and must be reconnected by a person.',
    'channel_unreachable': 'The configured Telegram storage chat cannot be used (access denied or not found).',
    'telegram_rate_limited': 'Telegram is rate limiting this account; try again later.',
    'telegram_unreachable': 'Telegram cannot be reached from the server.',
    'credentials_unreadable': 'Stored Telegram credentials cannot be decrypted (DJANGO_SECRET_KEY changed?); reconnect Telegram.',
    'telegram_not_configured': 'TELEGRAM_API_ID / TELEGRAM_API_HASH are not configured on the server.',
    'storage_not_connected': 'The storage account is not connected.',
}


class StorageUnavailable(Exception):
    """Storage is down for a known reason. Surfaces as HTTP 503 with a reason and Retry-After."""

    def __init__(self, reason, retry_after=30, message=None):
        self.reason = reason
        self.retry_after = int(retry_after)
        self.message = message or REASON_MESSAGES.get(reason, 'Storage is temporarily unavailable.')
        super().__init__(f"{reason}: {self.message}")


class StorageNotConnected(Exception):
    """The user has not connected a storage account. Surfaces as HTTP 409."""

    def __init__(self, message=None):
        self.message = message or "Connect your Telegram account in Settings → My storage to upload."
        super().__init__(self.message)
