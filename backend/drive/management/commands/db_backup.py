import os
import sys
import gzip
import shutil
import urllib.request
import datetime
import subprocess
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from config.env_schema import config


class Command(BaseCommand):
    help = 'Performs a compressed PostgreSQL backup and dispatches it to Telegram Cloud'

    def add_arguments(self, parser):
        parser.add_argument('--keep-local', action='store_true', help='Keep local backup file after sending to Telegram')

    def handle(self, *args, **options):
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = settings.BASE_DIR / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        sql_file = backup_dir / f"db_{config.DB_NAME}_{timestamp}.sql"
        gz_file = backup_dir / f"db_{config.DB_NAME}_{timestamp}.sql.gz"

        # Determine pg_dump executable (cross-platform)
        pg_dump_bin = shutil.which("pg_dump")
        if not pg_dump_bin:
            # Fallback for Windows default installation
            win_path = Path(r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe")
            if win_path.exists():
                pg_dump_bin = str(win_path)
            else:
                pg_dump_bin = "pg_dump"

        cmd = [
            pg_dump_bin,
            "-U", config.DB_USER,
            "-h", config.DB_HOST,
            "-p", str(config.DB_PORT),
            "--file", str(sql_file),
            config.DB_NAME
        ]

        self.stdout.write(f"Starting PostgreSQL backup of '{config.DB_NAME}'...")
        env = os.environ.copy()
        env["PGPASSWORD"] = config.DB_PASSWORD

        try:
            subprocess.run(cmd, env=env, check=True)
            self.stdout.write(f"Dump complete. Compressing with gzip...")
            
            with open(sql_file, 'rb') as f_in, gzip.open(gz_file, 'wb', compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)
            sql_file.unlink(missing_ok=True)
            
            size_kb = round(gz_file.stat().st_size / 1024, 2)
            self.stdout.write(self.style.SUCCESS(f"Compressed backup: {gz_file.name} ({size_kb} KB)"))

            # Dispatch to Telegram if configured
            bot_token = config.TELEGRAM_BOT_TOKEN
            chat_id = config.TELEGRAM_STORAGE_CHAT_ID

            if bot_token and chat_id:
                self.stdout.write("Dispatching backup archive to Telegram Cloud...")
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
                    f"📦 Database Backup: {config.DB_NAME}\r\nDate: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\r\nSize: {size_kb} KB\r\n"
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="document"; filename="{gz_file.name}"\r\n'
                    f"Content-Type: application/gzip\r\n\r\n"
                ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

                req = urllib.request.Request(url, data=body)
                req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

                with urllib.request.urlopen(req, timeout=30) as resp:
                    if resp.status == 200:
                        self.stdout.write(self.style.SUCCESS("Backup successfully preserved in Telegram Cloud!"))
                        if not options.get('keep_local'):
                            gz_file.unlink(missing_ok=True)
            else:
                self.stdout.write(self.style.WARNING("Telegram credentials not configured; preserved locally only."))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Backup failed: {e}"))
