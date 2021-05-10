#!/bin/bash

set -eu -o pipefail

export PATH=$HOME/.local/bin:$PATH

if [[ -z "${ENV_NAME}" ]]; then
    echo "ENV_NAME must be set prior to running this script."
    exit 1
fi

if [ $ENV_NAME = "prod" ]; then
    echo "This script should not be run in the production environment."
    exit 1
fi

POSTGRESQL_PW="$(aws secretsmanager get-secret-value --region us-east-1 --secret-id crowd/${ENV_NAME}/DB/MasterUserPassword | python -c 'import json,sys;Secret=json.load(sys.stdin);SecretString=json.loads(Secret["SecretString"]);print(SecretString["password"])')"
POSTGRESQL_HOST="$(aws ssm get-parameter --region us-east-1 --name /concordia/${ENV_NAME}/db.url | python -c 'import json,sys;ParameterInput=json.load(sys.stdin);Parameter=ParameterInput["Parameter"];print(Parameter["Value"])')"
DUMP_FILE=concordia.dmp

aws s3 cp s3://crowd-deployment/database-dumps/concordia.latest.dmp ${DUMP_FILE}

echo "${POSTGRESQL_HOST}:5432:*:concordia:${POSTGRESQL_PW}" > ~/.pgpass
chmod 600 ~/.pgpass

aws s3 sync s3://crowd-content s3://crowd-${ENV_NAME}-content

psql -U concordia -h "$POSTGRESQL_HOST" -d postgres -c "select pg_terminate_backend(pid) from pg_stat_activity where datname='concordia';"
psql -U concordia -h "$POSTGRESQL_HOST" -d postgres -c "drop database concordia;"
pg_restore --create -U concordia -h "${POSTGRESQL_HOST}" -Fc --dbname=postgres --no-owner --no-acl "${DUMP_FILE}"
echo $?
