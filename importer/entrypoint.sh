#!/bin/bash

set -e -u # Exit immediately for unhandled errors or undefined variables

mkdir -p /app/logs
touch /app/logs/concordia.log

#  To avoid trace and reporting of errors in the X-Ray SDK
export AWS_XRAY_CONTEXT_MISSING=LOG_ERROR

echo "Running celery worker"
celery -A concordia worker -l info -c 10
