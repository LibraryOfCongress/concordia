#!/bin/bash

set -eu -o pipefail

# aws cloudformation create-stack --region us-east-1 --stack-name $ENV_NAME-bastionhosts --template-url https://s3.amazonaws.com/crowd-deployment/infrastructure/bastion-hosts.yaml --parameters ParameterKey=EnvironmentName,ParameterValue=$ENV_NAME ParameterKey=KeyPairName,ParameterValue=rstorey@loc.gov --disable-rollback
# aws cloudformation delete-stack --region us-east-1 --stack-name $ENV_NAME-bastionhosts

if [[ -z "${ENV_NAME}" ]]; then
    echo "ENV_NAME must be set prior to running this script."
    exit 1
fi

if [ $ENV_NAME != "prod" ]; then
    echo "This script should only be run in the production environment."
    exit 1
fi

TODAY=$(date +%Y%m%d)
POSTGRESQL_PW="$(aws secretsmanager get-secret-value --region us-east-1 --secret-id crowd/${ENV_NAME}/DB/MasterUserPassword | python -c 'import json,sys;Secret=json.load(sys.stdin);SecretString=json.loads(Secret["SecretString"]);print(SecretString["password"])')"
POSTGRESQL_HOST="$(aws ssm get-parameter-value --region us-east-1 --name /concordia/${ENV_NAME}/db.url | python -c 'import json,sys;Parameter=json.load(sys.stdin);ParameterString=json.loads(Parameter["Parameter"]);print(ParameterString["Value"])')"
DUMP_FILE=concordia.dmp

echo "${POSTGRESQL_HOST}:5432:*:concordia:${POSTGRESQL_PW}" > ~/.pgpass
chmod 600 ~/.pgpass

pg_dump -Fc --clean --create --no-owner --no-acl -U concordia -h "${POSTGRESQL_HOST}" concordia -f "${DUMP_FILE}"

if [ -s $DUMP_FILE ]; then
    aws s3 cp "${DUMP_FILE}" "s3://crowd-deployment/database-dumps/concordia.${TODAY}.dmp"
    aws s3 cp "${DUMP_FILE}" s3://crowd-deployment/database-dumps/concordia.latest.dmp
fi
