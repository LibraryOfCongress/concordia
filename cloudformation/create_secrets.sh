#!/bin/bash

set -eu

# If you create a new set of secrets using a new ENV_NAME here,
# then add the new ENV_NAME option to the list of allowed options in
# master.yaml and infrastructure/fargate-cluster.yaml

export ENV_NAME=cftest2

export DJANGO_SECRET_KEY=
export DB_PASSWORD=
export KMS_KEY_ARN=arn:aws:kms:us-east-1:619333082511:key/d300e73d-9170-4001-933a-37af0bcdb956

aws secretsmanager create-secret --name "crowd/${ENV_NAME}/Django/SecretKey" --kms-key-id "${KMS_KEY_ARN}" --secret-string "{\"DjangoSecretKey\": \"${DJANGO_SECRET_KEY}\"}"

aws secretsmanager create-secret --name "crowd/${ENV_NAME}/DB/MasterUserPassword" --kms-key-id "${KMS_KEY_ARN}" --secret-string "{\"username\": \"concordia\",\"engine\": \"postgres\",\"port\": 5432,\"dbname\": \"concordia\",\"password\": \"${DB_PASSWORD}\"}"

# aws secretsmanager create-secret --name "concordia/SMTP" --kms-key-id "${KMS_KEY_ARN}" --secret-string '{"Hostname": "email-smtp.us-east-1.amazonaws.com","Username": "","Password": ""}'
