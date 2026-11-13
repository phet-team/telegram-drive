"""
Model signals for the drive app. Connected from DriveConfig.ready().
"""
import logging

from django.conf import settings
from django.db.models.signals import pre_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL)
def logout_storage_on_user_delete(sender, instance, **kwargs):
    """
    Before a user is deleted, log their own Telegram session out so the session
    cannot survive server-side. Best effort: 10 s cap, never raises, never blocks the delete.
    """
    account = getattr(instance, 'storage_account', None)
    if account is None or not account.has_session:
        return
    try:
        from storage_engine.secrets import decrypt

        session_str = decrypt(account.session_string_enc)
    except Exception:
        logger.warning("Storage session for user id=%s is unreadable; skipping Telegram logout", instance.id)
        return
    from storage_engine import login
    login.logout_client(session_str)
