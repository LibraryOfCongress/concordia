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

# FIXME: move this logic into a management command which creates the superuser if none exists and sets a password which will not be stored, forcing use of the forgot password reset mechanism
#    echo Creating admin user
#    ./manage.py shell -c "from django.contrib.auth.models import User;from django.contrib.auth.models import Group; User.objects.create_superuser('admin', 'admin@example.com', '$CONCORDIA_ADMIN_PW');Group.objects.create(name='CM')"

#    echo Running indexing
#    ./manage.py search_index --rebuild -f

echo Running Django dev server
gunicorn --log-level=warn --bind 0.0.0.0:80 --workers=4 concordia.wsgi
