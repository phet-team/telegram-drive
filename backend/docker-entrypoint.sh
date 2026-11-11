#!/bin/sh
set -e

echo "==> Running database migrations..."
python manage.py migrate --noinput

if [ "$STORAGE_SELFTEST_ON_START" = "1" ]; then
  echo "==> Running storage self-test (non-fatal)..."
  python manage.py storage_selftest --size-mb 8 || true
fi

echo "==> Starting application..."
exec "$@"
