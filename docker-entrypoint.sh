#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec daphne -b 0.0.0.0 -p "${PORT:-10000}" config.asgi:application
