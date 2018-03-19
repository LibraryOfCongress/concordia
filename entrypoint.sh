manage.py migrate
manage.py collectstatic --clear --noinput -v0
manage.py runserver 0:80
# gunicorn -c gunicorn.conf concordia.wsgi:application
