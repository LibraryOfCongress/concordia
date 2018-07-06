#!/bin/bash

./manage.py migrate
./manage.py shell -c "from django.contrib.auth.models import User; User.objects.create_superuser('admin', 'admin@example.com', '$CONCORDIA_ADMIN_PW')"


