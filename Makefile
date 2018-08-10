include .env

.PHONY: create-docker-sentry-network
create-docker-sentry-network:
	docker network create sentry 2>>/dev/null || true

.PHONY: up increase-elk-max-map-count
increase-elk-max-map-count:
	bash ./elk/increase_max_map_count.sh
up: 	increase-elk-max-map-count create-docker-sentry-network
	docker-compose -f sentry-docker-compose.yml up -d sentry_redis db
	docker-compose -f sentry-docker-compose.yml run --rm wait_sentry_postgres
	docker-compose -f sentry-docker-compose.yml run --rm wait_sentry_redis
	docker-compose -f sentry-docker-compose.yml run --rm sentry sentry upgrade --noinput
	docker-compose -f sentry-docker-compose.yml run --rm sentry sentry createuser \
		--email user@example.com \
		--password ${SENTRY_PW} \
		--superuser --no-input
	docker-compose up -d elk
	docker-compose run --rm wait_elk
	docker-compose -f sentry-docker-compose.yml -f prometheus-docker-compose.yml -f docker-compose.yml up -d


.PHONY: clean
clean:
	docker network rm sentry 2>>/dev/null || true
	docker-compose -f sentry-docker-compose.yml down -v --remove-orphans
	rm -rf postgresql-data/


