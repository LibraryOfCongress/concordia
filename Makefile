include .env

.PHONY: create-docker-sentry-network
create-docker-sentry-network:
	docker network create sentry 2>>/dev/null || true

.PHONY: up increase-elk-max-map-count
increase-elk-max-map-count:
	bash ./elk/increase_max_map_count.sh
firstup: increase-elk-max-map-count create-docker-sentry-network
	docker-compose -f docker-compose-sentry.yml up -d sentry_redis sentrydb
	docker-compose -f docker-compose-sentry.yml run --rm wait_sentry_postgres
	docker-compose -f docker-compose-sentry.yml run --rm wait_sentry_redis
	docker-compose -f docker-compose-sentry.yml run --rm sentry sentry upgrade --noinput
	docker-compose -f docker-compose-sentry.yml run --rm sentry sentry createuser \
		--email user@example.com \
		--password ${SENTRY_PW} \
		--superuser --no-input
	docker-compose up -d elk
	docker-compose run --rm wait_elk
	docker-compose -f docker-compose-sentry.yml -f docker-compose-prometheus.yml -f docker-compose.yml up -d

allup:	create-docker-sentry-network
	docker-compose -f docker-compose-sentry.yml up -d sentry_redis sentrydb
	docker-compose -f docker-compose-sentry.yml run --rm wait_sentry_postgres
	docker-compose -f docker-compose-sentry.yml run --rm wait_sentry_redis
	docker-compose -f docker-compose-sentry.yml run --rm sentry sentry upgrade --noinput
	docker-compose up -d elk
	docker-compose run --rm wait_elk
	docker-compose -f docker-compose-sentry.yml -f docker-compose-prometheus.yml -f docker-compose.yml up -d

devup:
	docker-compose up -d elk
	docker-compose run --rm wait_elk
	docker-compose up -d


clean:	down
	docker network rm sentry 2>>/dev/null || true
	docker-compose -f docker-compose-sentry.yml \
		-f docker-compose-prometheus.yml -f docker-compose.yml down -v --remove-orphans
	rm -rf postgresql-data/

.PHONY: down
down:
	docker-compose -f docker-compose-sentry.yml \
		-f docker-compose-prometheus.yml -f docker-compose.yml down
