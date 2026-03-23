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

POSTGRESQL_PW="$(aws secretsmanager get-secret-value --region us-east-1 --secret-id crowd/${ENV_NAME}/DB/MasterUserPassword | python3 -c 'import json,sys;Secret=json.load(sys.stdin);SecretString=json.loads(Secret["SecretString"]);print(SecretString["password"])')"
POSTGRESQL_HOST="$(aws ssm get-parameter --region us-east-1 --name /concordia/${ENV_NAME}/db.url | python3 -c 'import json,sys;ParameterInput=json.load(sys.stdin);Parameter=ParameterInput["Parameter"];print(Parameter["Value"])')"
DUMP_FILE=concordia.dmp

aws s3 cp s3://crowd-deployment/database-dumps/concordia.latest.dmp ${DUMP_FILE}

echo "${POSTGRESQL_HOST}:5432:*:concordia:${POSTGRESQL_PW}" > ~/.pgpass
chmod 600 ~/.pgpass

aws s3 sync s3://crowd-content s3://crowd-${ENV_NAME}-content --delete

psql -U concordia -h "$POSTGRESQL_HOST" -d postgres -c "select pg_terminate_backend(pid) from pg_stat_activity where datname='concordia';"
psql -U concordia -h "$POSTGRESQL_HOST" -d postgres -c "drop database concordia with (force);"
pg_restore --create -U concordia -h "${POSTGRESQL_HOST}" -Fc --dbname=postgres --no-owner --no-acl "${DUMP_FILE}"
RETURNCODE=$?
echo $RETURNCODE

if [ $RETURNCODE = 0 ] && [ $ENV_NAME = "test" ]; then
    ECS_SERVICE="$(aws ecs list-services --region us-east-1 --cluster crowd-${ENV_NAME} | python3 -c 'import json,sys;ParameterInput=json.load(sys.stdin);Parameter=ParameterInput["serviceArns"];print(Parameter[0].split("/")[2])')"

    # If a feature branch env is running the number of services in the test cluster increases.
    NUMBER_OF_SERVICES="$(aws ecs list-services --region us-east-1 --cluster crowd-test | python3 -c 'import json,sys;ParameterInput=json.load(sys.stdin);Parameter=ParameterInput["serviceArns"];print(len(Parameter))')"
    if [ $NUMBER_OF_SERVICES = 3 ];then
        # Normal
        ECS_SERVICE_2="$(aws ecs list-services --region us-east-1 --cluster crowd-${ENV_NAME} | python3 -c 'import json,sys;ParameterInput=json.load(sys.stdin);Parameter=ParameterInput["serviceArns"];print(Parameter[2].split("/")[2])')"
    else
        # Feature branch env exists.
        ECS_SERVICE_2="$(aws ecs list-services --region us-east-1 --cluster crowd-${ENV_NAME} | python3 -c 'import json,sys;ParameterInput=json.load(sys.stdin);Parameter=ParameterInput["serviceArns"];print(Parameter[3].split("/")[2])')"
    fi

    aws ecs update-service --region us-east-1 --force-new-deployment --cluster crowd-${ENV_NAME} --service ${ECS_SERVICE}
    aws ecs update-service --region us-east-1 --force-new-deployment --cluster crowd-${ENV_NAME} --service ${ECS_SERVICE_2}
elif [ $RETURNCODE = 0 ]; then
    ECS_SERVICE="$(aws ecs list-services --region us-east-1 --cluster crowd-${ENV_NAME} | python3 -c 'import json,sys;ParameterInput=json.load(sys.stdin);Parameter=ParameterInput["serviceArns"];print(Parameter[0].split("/")[2])')"
    aws ecs update-service --region us-east-1 --force-new-deployment --cluster crowd-${ENV_NAME} --service ${ECS_SERVICE}
fi
