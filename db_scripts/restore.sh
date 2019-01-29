#!/bin/bash

# export ENV_NAME=dev
# aws cloudformation create-stack --region us-east-1 --stack-name $ENV_NAME-bastionhosts --template-url https://s3.amazonaws.com/crowd-deployment/infrastructure/bastion-hosts.yaml --parameters ParameterKey=EnvironmentName,ParameterValue=$ENV_NAME ParameterKey=KeyPairName,ParameterValue=rstorey@loc.gov --disable-rollback
# aws cloudformation delete-stack --region us-east-1 --stack-name $ENV_NAME-bastionhosts

export POSTGRESQL_PW=${POSTGRESQL_PW:-password}
export POSTGRESQL_HOST=${POSTGRESQL_HOST:-localhost}
export DUMP_FILE=/concordia.dmp

echo "$POSTGRESQL_HOST:5432:*:concordia:$POSTGRESQL_PW" >> ~/.pgpass
chmod 600 ~/.pgpass

psql -U concordia -h "$POSTGRESQL_HOST" -d postgres -c "select pg_terminate_backend(pid) from pg_stat_activity where datname='concordia';"
psql -U concordia -h "$POSTGRESQL_HOST" -d postgres -c "drop database concordia;"
pg_restore --create --clean -U concordia -h "${POSTGRESQL_HOST}" -Fc --dbname=postgres --no-owner --no-acl $DUMP_FILE
