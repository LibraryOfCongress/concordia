mkdir -p /app/logs
mkdir -p /concordia_images
mkdir ~/.aws

touch /app/logs/concordia.log

echo Running celery worker
celery -A concordia worker -l info

