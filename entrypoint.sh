#!/bin/bash

set -e -u # Exit immediately for unhandled errors or undefined variables

mkdir -p /app/logs
touch /app/logs/concordia.log

#echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running makemigrations"
#./manage.py makemigrations --merge --noinput

#echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running migrations"
#./manage.py migrate

#echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ensuring our base configuration is present in the database"
#./manage.py ensure_initial_site_configuration

#if [ -v SENTRY_BACKEND_DSN ]; then
    #echo "[$(date '+%Y-%m-%d %H:%M:%S')] Testing Sentry configuration"
    #echo "from sentry_sdk import capture_message;capture_message('This is a test event');" | ./manage.py shell
#fi

#echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running collectstatic"
#./manage.py collectstatic --clear --noinput -v0

#echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Django ASGI server"
#daphne -b 0.0.0.0 -p 80 concordia.asgi:application

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Launching bash shell"
exec /bin/bash
