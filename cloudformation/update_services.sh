#!/bin/bash

set -eu

CLUSTER_NAME=crowd-dev
AWS_REGION=us-east-1

export CLUSTER_NAME AWS_REGION

aws ecs update-service --cluster $CLUSTER_NAME --service concordia --force-new-deployment
