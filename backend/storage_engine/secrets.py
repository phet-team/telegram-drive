import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class CredentialsUnreadable(Exception):
    """A stored secret cannot be decrypted (SECRET_KEY rotated or data corrupted)."""


def _fernet() -> Fernet:
    digest = hashlib.sha256(b"storage-settings:" + settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise CredentialsUnreadable("stored secret cannot be decrypted with the current SECRET_KEY") from exc
