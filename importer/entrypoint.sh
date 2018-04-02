mkdir -p /app/logs
mkdir -p /concordia_images
mkdir ~/.aws

echo "[default]\naws_access_key_id=AKIAJZPWS3IJDRIQPC3A\naws_secret_access_key=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" >> ~/.aws/credentials

touch /app/logs/concordia.log

echo Running celery worker
celery -A concordia worker -l info

