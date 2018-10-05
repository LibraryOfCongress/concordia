#!/bin/bash

set -eu

# DEV ENVIRONMENT
# CLUSTER_NAME=crowd-dev
# SERVICE_NAME=crowd-dev-app-Service-PPFPP27E26LE

# TEST ENVIRONMENT
# CLUSTER_NAME=crowd-test2
# SERVICE_NAME=crowd-test-app-Service-KRK54VT16MJN

# STAGE ENVIRONMENT
CLUSTER_NAME=crowd-stage
SERVICE_NAME=crowd-stage-app-Service-EV9ZR04V07M1

# PROD ENVIRONMENT
# CLUSTER_NAME=crowd-prod
# SERVICE_NAME=crowd-prod-app-Service

AWS_REGION=us-east-1

export CLUSTER_NAME AWS_REGION SERVICE_NAME

aws ecs update-service --region $AWS_REGION --cluster $CLUSTER_NAME --service $SERVICE_NAME --force-new-deployment
