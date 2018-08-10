#!/bin/bash

set -e -u # Exit immediately for unhandled errors or undefined variables

source ./.env

mkdir -p /app/logs
touch /app/logs/concordia.log

echo Running makemigrations
./manage.py makemigrations --merge --noinput

echo Running migrations
./manage.py migrate

echo Running collectstatic
./manage.py collectstatic --clear --noinput -v0

echo Creating admin user
./manage.py shell -c "from django.contrib.auth.models import User; User.objects.create_superuser('admin', 'admin@example.com', '$CONCORDIA_ADMIN_PW')"

echo Running Django dev server
./manage.py runserver 0:80


