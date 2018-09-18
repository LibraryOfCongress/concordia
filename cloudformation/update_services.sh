#!/bin/bash

set -eu

CLUSTER_NAME=crowd-dev
AWS_REGION=us-east-1

export CLUSTER_NAME AWS_REGION

aws ecs register-task-definition --cli-input-json file://task_definitions.json

aws ecs update-service --cluster $CLUSTER_NAME --service concordia --force-new-deployment
