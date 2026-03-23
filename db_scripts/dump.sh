#!/bin/bash

set -eu -o pipefail

if [[ -z "${ENV_NAME}" ]]; then
    echo "ENV_NAME must be set prior to running this script."
    exit 1
fi

if [ $ENV_NAME != "prod" ]; then
    echo "This script should only be run in the production environment."
    exit 1
fi

TODAY=$(date +%Y%m%d)
if [[ "$TODAY" =~ (0101|0401|0701|1001)$ ]]; then
    TAGVALUE="true"
else
    TAGVALUE="false"
fi
POSTGRESQL_PW="$(aws secretsmanager get-secret-value --region us-east-1 --secret-id crowd/${ENV_NAME}/DB/MasterUserPassword | python3 -c 'import json,sys;Secret=json.load(sys.stdin);SecretString=json.loads(Secret["SecretString"]);print(SecretString["password"])')"
POSTGRESQL_HOST="$(aws ssm get-parameter --region us-east-1 --name /concordia/${ENV_NAME}/db.url | python3 -c 'import json,sys;ParameterInput=json.load(sys.stdin);Parameter=ParameterInput["Parameter"];print(Parameter["Value"])')"
DUMP_FILE=concordia.dmp

echo "${POSTGRESQL_HOST}:5432:*:concordia:${POSTGRESQL_PW}" > ~/.pgpass
chmod 600 ~/.pgpass

pg_dump -Fc --no-acl -U concordia -h "${POSTGRESQL_HOST}" concordia -f "${DUMP_FILE}"

if [ -s $DUMP_FILE ]; then
    aws s3 cp "${DUMP_FILE}" "s3://crowd-deployment/database-dumps/concordia.${TODAY}.dmp"
    aws s3 cp "${DUMP_FILE}" s3://crowd-deployment/database-dumps/concordia.latest.dmp
    aws s3api put-object-tagging --bucket 'crowd-deployment' --key database-dumps/concordia.${TODAY}.dmp --tagging '{"TagSet": [{ "Key": "first-dmp-of-quarter", "Value": "'${TAGVALUE}'" }]}'
    aws s3api put-object-tagging --bucket 'crowd-deployment' --key database-dumps/concordia.latest.dmp --tagging '{"TagSet": [{ "Key": "first-dmp-of-quarter", "Value": "'${TAGVALUE}'" }]}'
fi
echo $?
