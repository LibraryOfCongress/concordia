python manage.py migrate
python manage.py collectstatic --clear --noinput -v0

gunicorn -c gunicorn.conf dashboard.wsgi:application
