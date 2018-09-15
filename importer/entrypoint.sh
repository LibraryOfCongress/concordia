#!/bin/bash

set -e -u # Exit immediately for unhandled errors or undefined variables

source ./.env

export SENTRY_DSN SENTRY_PUBLIC_DSN CELERY_BROKER_URL DJANGO_SECRET_KEY POSTGRESQL_HOST S3_BUCKET_NAME AWS_DEFAULT_REGION

#POSTGRESQL_PW="$(aws ssm get-parameter --output=text --name /concordia/test/DB/MasterUserPassword --with-decryption --query "Parameter.Value")"

#export POSTGRESQL_PW SENTRY_DSN SENTRY_PUBLIC_DSN CELERY_BROKER_URL

mkdir -p /app/logs
touch /app/logs/concordia.log

echo Running celery worker
celery -A concordia worker -l info -c 10

