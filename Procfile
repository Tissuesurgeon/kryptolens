web: gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120
worker: celery -A config worker -l info
beat: celery -A config beat -l info
