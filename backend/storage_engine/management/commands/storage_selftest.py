import logging

from django.core.management.base import BaseCommand, CommandError

from storage_engine.selftest import run_selftest

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Upload, download, verify and delete random bytes through the storage engine."

    def add_arguments(self, parser):
        parser.add_argument('--size-mb', type=int, default=8, help="Payload size, 1..16 MB (default 8)")

    def handle(self, *args, **options):
        size_mb = options['size_mb']
        if not 1 <= size_mb <= 16:
            raise CommandError("--size-mb must be between 1 and 16")
        result = run_selftest(size_mb)
        if result['ok']:
            line = f"STORAGE SELFTEST OK size={size_mb}MB up={result['up_s']}s down={result['down_s']}s"
            logger.info(line)
            self.stdout.write(line)
            return
        line = f"STORAGE SELFTEST FAILED step={result['failed_step']} reason={result['reason']}"
        logger.error(line)
        raise CommandError(line)
