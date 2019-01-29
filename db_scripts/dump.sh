#!/bin/bash

# export ENV_NAME=prod
# aws cloudformation create-stack --region us-east-1 --stack-name $ENV_NAME-bastionhosts --template-url https://s3.amazonaws.com/crowd-deployment/infrastructure/bastion-hosts.yaml --parameters ParameterKey=EnvironmentName,ParameterValue=$ENV_NAME ParameterKey=KeyPairName,ParameterValue=rstorey@loc.gov --disable-rollback
# aws cloudformation delete-stack --region us-east-1 --stack-name $ENV_NAME-bastionhosts

export TODAY=20190129
export POSTGRESQL_PW=${POSTGRESQL_PW:-password}
export POSTGRESQL_HOST=${POSTGRESQL_HOST:-localhost}
export DUMP_FILE=concordia.dmp

echo "$POSTGRESQL_HOST:5432:*:concordia:$POSTGRESQL_PW" >> ~/.pgpass
chmod 600 ~/.pgpass

pg_dump -Fc --clean --create --no-owner --no-acl -U concordia -h "$POSTGRESQL_HOST" concordia -f "$DUMP_FILE"
aws s3 cp "$DUMP_FILE" s3://crowd-deployment/database-dumps/concordia.$TODAY.dmp
aws s3 cp "$DUMP_FILE" s3://crowd-deployment/database-dumps/concordia.latest.dmp
