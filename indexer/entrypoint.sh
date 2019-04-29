#!/bin/bash

set -e -u # Exit immediately for unhandled errors or undefined variables


mkdir -p /app/logs
touch /app/logs/concordia.log
touch /app/logs/concordia-celery.log


echo "Running indexing"
./manage.py search_index --rebuild -f
