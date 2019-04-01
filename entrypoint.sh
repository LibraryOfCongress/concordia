#!/bin/bash

set -e -u # Exit immediately for unhandled errors or undefined variables

mkdir -p /app/logs
touch /app/logs/concordia.log

echo "Running makemigrations"
./manage.py makemigrations --merge --noinput

echo "Running migrations"
./manage.py migrate

echo "Ensuring our base configuration is present in the database"
./manage.py ensure_initial_site_configuration

if [ -v SENTRY_BACKEND_DSN ]; then
    echo "Testing Sentry configuration"
    ./manage.py raven test
fi

echo "Running collectstatic"
./manage.py collectstatic --clear --noinput -v0

echo "Running Django ASGI server"
daphne -b 0.0.0.0 -p 80 concordia.asgi:application
