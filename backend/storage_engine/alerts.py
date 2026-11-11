"""
Storage alerts: ok -> down alerts immediately, repeats at most every
`alert_min_interval_minutes` while down, one "recovered" message on down -> ok.

State lives on the StorageSettings row (shared by all gunicorn workers). Sending never
raises and never blocks a request: it runs in a daemon thread with a 5 s timeout.
Webhook URLs and the bot token are secrets: they are never logged, and exceptions are
logged by class name only (requests includes the URL in its messages).
"""
import ipaddress
import logging
import socket
import threading
from datetime import timedelta
from urllib.parse import urlparse

import requests
from django.db import transaction
from django.utils import timezone

from config.env_schema import config
from storage_engine.errors import REASON_MESSAGES

logger = logging.getLogger(__name__)

SEND_TIMEOUT = 5
_known_host = ''


def _run_in_background(fn):
    """Indirection so tests can run the sender inline."""
    threading.Thread(target=fn, daemon=True, name='StorageAlertSender').start()


def _post(url, **kwargs):
    """HTTP POST used for every channel. Redirects are refused (SSRF)."""
    return requests.post(url, timeout=SEND_TIMEOUT, allow_redirects=False, **kwargs)


def _resolve(host):
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def remember_host(base_url):
    """Remembers the public origin of the last request so alerts can link to the settings page."""
    global _known_host
    _known_host = base_url.rstrip('/')


def settings_url():
    base = (config.PUBLIC_URL or _known_host).rstrip('/')
    return f"{base}/settings/storage" if base else ''


# -- SSRF guard -----------------------------------------------------------------------------

def validate_webhook_url(url):
    """https only; every resolved address must be globally routable. Raises ValueError."""
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        raise ValueError("Webhook URL must use https.")
    host = parsed.hostname
    if not host:
        raise ValueError("Webhook URL has no host.")
    try:
        addresses = _resolve(host)
    except OSError as exc:
        raise ValueError(f"Webhook host cannot be resolved ({type(exc).__name__}).") from exc
    if not addresses:
        raise ValueError("Webhook host did not resolve to any address.")
    for raw in addresses:
        ip = ipaddress.ip_address(raw.split('%')[0])
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise ValueError("Webhook URL must not point to a private, loopback, link-local or metadata address.")


# -- message building and delivery --------------------------------------------------------------

def build_message(state, reason=''):
    """Returns (title, message) for 'down' / 'ok' / 'test'."""
    if state == 'down':
        message = REASON_MESSAGES.get(reason, 'Storage is unavailable.')
        if reason in ('telegram_session_expired', 'credentials_unreadable'):
            url = settings_url()
            message += " Open Settings -> Storage -> Reconnect Telegram" + (f": {url}" if url else ".")
        return f"Telegram Drive storage is DOWN ({reason})", message
    if state == 'ok':
        return "Telegram Drive storage recovered", "Telegram storage is working again."
    return "Telegram Drive test alert", "This is a test alert from Telegram Drive."


def channels_from_row(row):
    return {
        'format': row.alert_format,
        'webhook_url': row.alert_webhook_url,
        'telegram_chat_id': row.alert_telegram_chat_id,
    }


def _check(response):
    if not 200 <= response.status_code < 300:
        return f"error: HTTP {response.status_code}"
    return "ok"


def _send_webhook(channels, title, message, reason, state):
    url, fmt = channels['webhook_url'], channels['format']
    try:
        validate_webhook_url(url)  # re-checked at send time
        if fmt == 'ntfy':
            response = _post(url, data=message.encode('utf-8'), headers={
                'Title': title, 'Priority': 'high' if state == 'down' else 'default',
            })
        else:
            if fmt == 'discord':
                body = {'content': f"{title}\n{message}"}
            elif fmt == 'slack':
                body = {'text': f"{title}\n{message}"}
            else:
                body = {'title': title, 'message': message, 'reason': reason,
                        'time': timezone.now().isoformat(), 'state': state}
            response = _post(url, json=body)
        return _check(response)
    except ValueError as exc:
        return f"error: {exc}"
    except Exception as exc:
        logger.warning("Alert webhook delivery failed: %s", type(exc).__name__)
        return f"error: {type(exc).__name__}"


def _send_telegram(channels, title, message):
    if not config.TELEGRAM_BOT_TOKEN:
        return "error: TELEGRAM_BOT_TOKEN is not configured"
    try:
        response = _post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={'chat_id': channels['telegram_chat_id'], 'text': f"{title}\n{message}"},
        )
        return _check(response)
    except Exception as exc:
        logger.warning("Alert Telegram DM failed: %s", type(exc).__name__)
        return f"error: {type(exc).__name__}"


def deliver(channels, title, message, reason='', state='down'):
    """Sends through every configured channel. Never raises. Returns {channel: 'ok' | 'error: ...'}."""
    results = {}
    if channels['webhook_url']:
        results['webhook'] = _send_webhook(channels, title, message, reason, state)
    if channels['telegram_chat_id']:
        results['telegram'] = _send_telegram(channels, title, message)
    for name, result in results.items():
        if result != 'ok':
            logger.warning("Storage alert channel %s: %s", name, result)
    return results


def _dispatch(channels, title, message, reason, state):
    if not channels['webhook_url'] and not channels['telegram_chat_id']:
        return
    _run_in_background(lambda: deliver(channels, title, message, reason, state))


def send_test(row):
    """Synchronous test through the saved channels; returns the per-channel result."""
    title, message = build_message('test')
    return deliver(channels_from_row(row), title, message, reason='test', state='test')


# -- state machine ------------------------------------------------------------------------

def _locked_row():
    from drive.models import StorageSettings

    StorageSettings.get_solo()
    return StorageSettings.objects.select_for_update().get(pk=1)


def report_failure(reason):
    """Records a failed check/operation. Returns True when an alert was dispatched."""
    from drive.models import StorageSettings

    now = timezone.now()
    with transaction.atomic():
        row = _locked_row()
        interval = timedelta(minutes=row.alert_min_interval_minutes)
        if row.alert_state != StorageSettings.ALERT_DOWN:
            send = True
        else:
            send = row.last_alert_at is None or now - row.last_alert_at >= interval
        row.alert_state = StorageSettings.ALERT_DOWN
        row.last_check_at, row.last_check_ok, row.last_check_reason = now, False, reason
        fields = ['alert_state', 'last_check_at', 'last_check_ok', 'last_check_reason']
        if send:
            row.last_alert_at = now
            fields.append('last_alert_at')
        row.save(update_fields=fields)
        channels = channels_from_row(row)
    if send:
        title, message = build_message('down', reason)
        _dispatch(channels, title, message, reason, 'down')
    return send


def report_ok():
    """Records a successful check. Returns True when a "recovered" message was dispatched."""
    from drive.models import StorageSettings

    now = timezone.now()
    with transaction.atomic():
        row = _locked_row()
        was_down = row.alert_state == StorageSettings.ALERT_DOWN
        row.alert_state = StorageSettings.ALERT_OK
        row.last_check_at, row.last_check_ok, row.last_check_reason = now, True, ''
        row.save(update_fields=['alert_state', 'last_check_at', 'last_check_ok', 'last_check_reason'])
        channels = channels_from_row(row)
    if was_down:
        title, message = build_message('ok')
        _dispatch(channels, title, message, '', 'ok')
    return was_down
