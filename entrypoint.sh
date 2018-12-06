#!/bin/bash

set -e -u # Exit immediately for unhandled errors or undefined variables

mkdir -p /app/logs
touch /app/logs/concordia.log

echo Running makemigrations
./manage.py makemigrations --merge --noinput

echo Running migrations
./manage.py migrate

echo "Ensuring our base configuration is present in the database"
./manage.py ensure_initial_site_configuration

echo "Testing Sentry configuration"
./manage.py raven test

echo Running collectstatic
./manage.py collectstatic --clear --noinput -v0

#    echo Running indexing
#    ./manage.py search_index --rebuild -f

echo Running Django dev server
gunicorn --log-level=warn --bind 0.0.0.0:80 --workers=4 concordia.wsgi
