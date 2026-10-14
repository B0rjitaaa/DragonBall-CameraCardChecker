#!/bin/sh
set -e

# Solo el servicio "backend" migra; worker y beat arrancan directamente.
if [ "$RUN_MIGRATIONS" = "1" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput >/dev/null
    python manage.py ensure_superuser
fi

exec "$@"
