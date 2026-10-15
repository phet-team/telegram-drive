import time
import hmac
import hashlib
from config.env_schema import config


from typing import Optional


def generate_media_token(grant_type_or_user_id, grant_id_or_file_id, file_id: str = None, expires_in_seconds: int = 1800) -> str:
    """
    Generate an HMAC-SHA256 signature for media streaming (<video>, <img>, PDF).
    Supports grant types: 'user' (ACL grant) or 'share' (public share link grant).
    Format: grant_type.grant_id.file_id.expires_at.signature
    """
    if file_id is None:
        # Legacy call: generate_media_token(user_id, file_id, expires_in_seconds)
        grant_type = 'user'
        grant_id = str(grant_type_or_user_id)
        actual_file_id = str(grant_id_or_file_id)
    else:
        grant_type = str(grant_type_or_user_id)
        grant_id = str(grant_id_or_file_id)
        actual_file_id = str(file_id)

    expires_at = int(time.time()) + expires_in_seconds
    msg = f"{grant_type}:{grant_id}:{actual_file_id}:{expires_at}"
    key = config.JWT_SECRET_KEY.encode('utf-8')
    sig = hmac.new(key, msg.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{grant_type}.{grant_id}.{actual_file_id}.{expires_at}.{sig}"


def parse_and_verify_media_token(token: str, expected_file_id: str) -> Optional[dict]:
    """Verify HMAC signature and expiration, returning grant metadata."""
    try:
        parts = token.split('.')
        if len(parts) == 5:
            grant_type, grant_id, file_id, expires_at_str, sig = parts
            if file_id != str(expected_file_id):
                return None
            expires_at = int(expires_at_str)
            if time.time() > expires_at:
                return None
            msg = f"{grant_type}:{grant_id}:{file_id}:{expires_at}"
            key = config.JWT_SECRET_KEY.encode('utf-8')
            expected_sig = hmac.new(key, msg.encode('utf-8'), hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected_sig, sig):
                return {
                    'grant_type': grant_type,
                    'grant_id': grant_id,
                    'file_id': file_id,
                    'expires_at': expires_at,
                }
            return None
        elif len(parts) == 2:
            expires_at_str, sig = parts
            expires_at = int(expires_at_str)
            if time.time() > expires_at:
                return None
            return {'grant_type': 'legacy', 'expires_at': expires_at, 'sig': sig}
        return None
    except Exception:
        return None


def verify_media_token(user_id: int, file_id: str, token: str) -> bool:
    """Legacy helper for backward compatibility."""
    parsed = parse_and_verify_media_token(token, file_id)
    if not parsed:
        return False
    if parsed.get('grant_type') == 'user':
        return parsed.get('grant_id') == str(user_id)
    return True
