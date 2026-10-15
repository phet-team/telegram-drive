import time
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Cleans up orphaned temporary chunks and upload fragments older than specified hours'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Delete temporary chunks older than this number of hours (default: 24)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        hours = options['hours']
        dry_run = options['dry_run']
        cutoff_time = time.time() - (hours * 3600)

        temp_dir = settings.CHUNK_CACHE_DIR
        if not temp_dir.exists():
            self.stdout.write(self.style.SUCCESS("No temporary chunks directory found."))
            return

        deleted_count = 0
        deleted_bytes = 0

        self.stdout.write(f"Scanning for temporary chunks older than {hours} hours in {temp_dir}...")

        for item in temp_dir.iterdir():
            # Skip hot_cache directory as it has its own LRU eviction
            if item.is_dir() and item.name == 'hot_cache':
                continue

            if item.is_file():
                try:
                    stat = item.stat()
                    if stat.st_mtime < cutoff_time:
                        file_size = stat.st_size
                        if not dry_run:
                            item.unlink(missing_ok=True)
                        deleted_count += 1
                        deleted_bytes += file_size
                except Exception as e:
                    self.stderr.write(f"Error inspecting {item.name}: {e}")

        freed_mb = round(deleted_bytes / (1024 * 1024), 2)
        mode_str = "[DRY-RUN] Would remove" if dry_run else "Successfully removed"
        self.stdout.write(self.style.SUCCESS(
            f"{mode_str} {deleted_count} orphaned chunks, freeing {freed_mb} MB of disk space."
        ))

        # Database Cleanup: Release reserved quota on expired UploadSessions
        from drive.models import UploadSession
        from django.utils import timezone
        from django.db import transaction

        expired_sessions = UploadSession.objects.filter(
            status='UPLOADING',
            expires_at__lt=timezone.now()
        ).select_related('user')

        expired_count = 0
        released_bytes = 0
        for session in expired_sessions:
            if not dry_run:
                with transaction.atomic():
                    user = session.user
                    user.refresh_from_db()
                    user.storage_reserved = max(0, user.storage_reserved - session.total_size)
                    user.save(update_fields=['storage_reserved'])
                    session.status = 'CANCELLED'
                    session.save(update_fields=['status', 'updated_at'])
            expired_count += 1
            released_bytes += session.total_size

        released_mb = round(released_bytes / (1024 * 1024), 2)
        release_mode_str = "[DRY-RUN] Would release" if dry_run else "Successfully cancelled and released"
        self.stdout.write(self.style.SUCCESS(
            f"{release_mode_str} {expired_count} expired upload sessions, returning {released_mb} MB of reserved quota."
        ))
