#!/bin/bash

set -e -u # Exit immediately for unhandled errors or undefined variables

mkdir -p /app/logs
touch /app/logs/concordia.log

echo "Running celerybeat"
celery -A concordia beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler