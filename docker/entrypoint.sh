#!/bin/sh
set -eu
ROLE="${1:-web}"

python manage.py wait_for_db
python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ "$ROLE" = "web" ]; then
  PORT="${PORT:-8000}"
  exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT}" --workers 2 --timeout 120
fi
if [ "$ROLE" = "worker" ]; then
  exec celery -A config worker -l info
fi
if [ "$ROLE" = "beat" ]; then
  exec celery -A config beat -l info
fi
if [ "$ROLE" = "m0" ]; then
  exec python spikes/m0_chain.py
fi
exec "$@"
