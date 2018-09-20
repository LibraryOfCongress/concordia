include .env

.PHONY: create-docker-sentry-network
create-docker-sentry-network:
	docker network create sentry 2>>/dev/null || true

.PHONY: increase-elk-max-map-count
increase-elk-max-map-count:
	bash ./elk/increase_max_map_count.sh

.PHONY: firstup
firstup: increase-elk-max-map-count create-docker-sentry-network
	docker-compose -f docker-compose-sentry.yml up -d sentry_redis sentrydb
	docker-compose -f docker-compose-sentry.yml run --rm wait_sentry_postgres
	docker-compose -f docker-compose-sentry.yml run --rm wait_sentry_redis
	docker-compose -f docker-compose-sentry.yml run --rm sentry sentry upgrade --noinput
	docker-compose -f docker-compose-sentry.yml run --rm sentry sentry createuser \
		--email user@example.com \
		--password ${SENTRY_PW} \
		--superuser --no-input
	docker-compose -f docker-compose-elk.yml -f docker-compose.yml up -d elk
	docker-compose -f docker-compose-elk.yml -f docker-compose-sentry.yml -f docker-compose-elk.yml -f docker-compose-prometheus.yml -f docker-compose.yml up -d
	adminuser

.PHONY: adminuser
adminuser:
	docker-compose -f docker-compose.yml run --rm app ./manage.py shell -c "from django.contrib.auth.models import User;from django.contrib.auth.models import Group; User.objects.create_superuser('admin', 'crowd@loc.gov', '${CONCORDIA_ADMIN_PW}');Group.objects.create(name='CM')"

.PHONY: allup
allup:	create-docker-sentry-network
	docker-compose -f docker-compose-sentry.yml up -d sentry_redis sentrydb
	docker-compose -f docker-compose-sentry.yml run --rm wait_sentry_postgres
	docker-compose -f docker-compose-sentry.yml run --rm wait_sentry_redis
	docker-compose -f docker-compose-sentry.yml run --rm sentry sentry upgrade --noinput
	docker-compose -f docker-compose-elk.yml up -d elk
	docker-compose -f docker-compose-elk.yml run --rm wait_elk
	docker-compose -f docker-compose-elk.yml -f docker-compose-sentry.yml -f docker-compose-prometheus.yml -f docker-compose.yml up -d

.PHONY: devup
devup: 
	docker-compose -f docker-compose.yml -f docker-compose-elk.yml up -d elk
	docker-compose -f docker-compose.yml -f docker-compose-elk.yml up -d

.PHONY: down
down:
	docker-compose -f docker-compose-elk.yml -f docker-compose-sentry.yml \
		-f docker-compose-prometheus.yml -f docker-compose.yml down


.PHONY: clean
clean:	down
	docker network rm sentry 2>>/dev/null || true
	docker-compose -f docker-compose-elk.yml -f docker-compose-sentry.yml \
		-f docker-compose-prometheus.yml -f docker-compose.yml down -v --remove-orphans
	rm -rf postgresql-data/

