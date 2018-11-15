.PHONY: allup firstup adminuser devup down clean

firstup:
	docker-compose -f docker-compose.yml up -d
	adminuser

adminuser:
	docker-compose -f docker-compose.yml run --rm app ./manage.py shell -c "from django.contrib.auth.models import User; User.objects.create_superuser('admin', 'crowd@loc.gov', '${CONCORDIA_ADMIN_PW}')"

allup:
	docker-compose -f docker-compose.yml up -d

devup:
	docker-compose -f docker-compose.yml up -d

down:
	docker-compose -f docker-compose.yml down

clean:	down
	docker-compose -f docker-compose.yml down -v --remove-orphans
	rm -rf postgresql-data/
