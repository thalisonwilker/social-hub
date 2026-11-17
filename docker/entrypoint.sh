#!/bin/sh
# Prepara o banco e inicia o processo principal (Gunicorn por padrão).
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
    python manage.py ensure_admin
fi

exec "$@"
