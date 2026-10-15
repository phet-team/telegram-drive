"""
Automated PostgreSQL Database Backup Script for Telegram Cloud Storage.
Dumps PostgreSQL database, compresses it with gzip, and sends it directly
to your Telegram chat or storage channel as an off-site backup.
Zero-cost, infinite offsite database preservation.
"""

import os
import sys
import gzip
import shutil
import logging
import datetime
import subprocess
from pathlib import Path

# Add backend directory to path so config can be imported
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from config.env_schema import config

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def perform_backup():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backend_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    sql_file = backup_dir / f"db_{config.DB_NAME}_{timestamp}.sql"
    gz_file = backup_dir / f"db_{config.DB_NAME}_{timestamp}.sql.gz"

    logger.info(f"Starting database backup for '{config.DB_NAME}'...")

    # 1. Execute pg_dump
    pg_env = os.environ.copy()
    pg_env["PGPASSWORD"] = config.DB_PASSWORD

    cmd = [
        "pg_dump",
        "-h", config.DB_HOST,
        "-p", str(config.DB_PORT),
        "-U", config.DB_USER,
        "-d", config.DB_NAME,
        "-F", "p",  # Plain-text SQL
        "-f", str(sql_file)
    ]

    try:
        subprocess.run(cmd, env=pg_env, check=True, capture_output=True, text=True)
        logger.info(f"pg_dump completed: {sql_file.name}")
    except FileNotFoundError:
        logger.error("pg_dump binary not found in PATH. Please ensure PostgreSQL client tools are installed.")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"pg_dump failed: {e.stderr}")
        return False

    # 2. Compress with gzip
    try:
        with open(sql_file, "rb") as f_in, gzip.open(gz_file, "wb", compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)
        sql_file.unlink(missing_ok=True)
        size_kb = round(gz_file.stat().st_size / 1024, 2)
        logger.info(f"Compressed backup created: {gz_file.name} ({size_kb} KB)")
    except Exception as e:
        logger.error(f"Failed to compress backup: {e}")
        return False

    # 3. Send to Telegram via Bot API
    bot_token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_STORAGE_CHAT_ID

    if not bot_token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_STORAGE_CHAT_ID not configured. Backup saved locally only.")
        return True

    logger.info("Sending database backup to Telegram...")
    try:
        import urllib.request
        import mimetypes

        url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"

        with open(gz_file, "rb") as f:
            file_bytes = f.read()

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
            f"{chat_id}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="caption"\r\n\r\n'
            f"📦 Automated DB Backup: {config.DB_NAME}\r\nDate: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\r\nSize: {size_kb} KB\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="document"; filename="{gz_file.name}"\r\n'
            f"Content-Type: application/gzip\r\n\r\n"
        ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(url, data=body)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                logger.info("Backup successfully dispatched to Telegram Cloud!")
                # Keep local backups clean: remove local archive after successful cloud dispatch
                gz_file.unlink(missing_ok=True)
                return True
            else:
                logger.warning(f"Telegram upload returned status {resp.status}")
                return False

    except Exception as e:
        logger.error(f"Failed to send backup to Telegram: {e}")
        return False


if __name__ == "__main__":
    success = perform_backup()
    sys.exit(0 if success else 1)
