#!/bin/bash

set -e

python manage.py migrate --no-input        # never makemigrations in prod
python manage.py collectstatic --no-input
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3