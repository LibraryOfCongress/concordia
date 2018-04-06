mkdir -p /app/logs
touch /app/logs/concordia.log

echo Running migrations
./manage.py migrate

echo Running collectstatic
./manage.py collectstatic --clear --noinput -v0

echo Running Django dev server
./manage.py runserver 0:80

# echo running gunicorn
# gunicorn -c gunicorn.conf concordia.wsgi:application

