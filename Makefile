include .env

.PHONY: create-docker-sentry-network
create-docker-sentry-network:
	docker network create sentry 2>>/dev/null || true

.PHONY: up
up: create-docker-sentry-network
	docker-compose up -d sentry_redis db
	docker-compose run --rm wait_sentry_postgres
	docker-compose run --rm wait_sentry_redis
	docker-compose run --rm sentry sentry upgrade --noinput
	docker-compose run --rm sentry sentry createuser \
		--email user@example.com \
		--password ${SENTRY_PW} \
		--superuser --no-input
	docker-compose up -d

.PHONY: clean
clean:
	docker network rm sentry 2>>/dev/null || true
	docker-compose down -v --remove-orphans
	rm -rf postgresql-data/


