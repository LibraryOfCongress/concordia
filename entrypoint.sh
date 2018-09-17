#!/bin/bash

set -e -u # Exit immediately for unhandled errors or undefined variables

source ./.env

export SENTRY_DSN SENTRY_PUBLIC_DSN CELERY_BROKER_URL DJANGO_SECRET_KEY POSTGRESQL_HOST S3_BUCKET_NAME AWS_DEFAULT_REGION

#POSTGRESQL_PW="$(aws ssm get-parameter --output=text --name /concordia/test/DB/MasterUserPassword --with-decryption --query "Parameter.Value")"

#export POSTGRESQL_PW SENTRY_DSN SENTRY_PUBLIC_DSN CELERY_BROKER_URL

mkdir -p /app/logs
touch /app/logs/concordia.log

echo Running makemigrations
./manage.py makemigrations --merge --noinput

echo Running migrations
./manage.py migrate

echo Running collectstatic
./manage.py collectstatic --clear --noinput -v0

#    echo Creating admin user
#    ./manage.py shell -c "from django.contrib.auth.models import User;from django.contrib.auth.models import Group; User.objects.create_superuser('admin', 'admin@example.com', '$CONCORDIA_ADMIN_PW');Group.objects.create(name='CM')"

#    echo Running indexing
#    ./manage.py search_index --rebuild -f

echo Running Django dev server
./manage.py runserver 0:80

