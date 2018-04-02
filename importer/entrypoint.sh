mkdir -p /app/logs
touch /app/logs/concordia.log

echo Running celery worker
celery -A concordia worker -l info

