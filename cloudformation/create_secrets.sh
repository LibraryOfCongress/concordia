#!/bin/bash

set -eu

# If you create a new set of secrets using a new ENV_NAME here,
# then add the new ENV_NAME option to the list of allowed options in
# master.yaml and infrastructure/fargate-cluster.yaml

export ENV_NAME=dev-fg

export DJANGO_SECRET_KEY=
export DB_PASSWORD=
export KMS_KEY_ARN=

aws secretsmanager create-secret --name "crowd/${ENV_NAME}/Django/SecretKey" --kms-key-id "${KMS_KEY_ARN}" --secret-string "{\"DjangoSecretKey\": \"${DJANGO_SECRET_KEY}\"}"

aws secretsmanager create-secret --name "crowd/${ENV_NAME}/DB/MasterUserPassword" --kms-key-id "${KMS_KEY_ARN}" --secret-string "{\"username\": \"concordia\",\"engine\": \"postgres\",\"port\": 5432,\"dbname\": \"concordia\",\"password\": \"${DB_PASSWORD}\"}"

# aws acm import-certificate --certificate ${CERTIFICATE} --certificate-chain ${CERTIFICATE_CHAIN}

aws secretsmanager create-secret --name "concordia/SMTP" --kms-key-id "${KMS_KEY_ARN}" --secret-string '{"Hostname": "email-smtp.us-east-1.amazonaws.com","Username": "","Password": ""}'

aws secretsmanager create-secret --name "crowd/SentryDSN" --kms-key-id "${KMS_KEY_ARN}" --secret-string '{"SentryDSN": "http://34db819263f34c28809da045f841f045@devops-sentry-public-lb-1114947433.us-east-1.elb.amazonaws.com/2"}'