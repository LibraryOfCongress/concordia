#!/bin/bash

set -eu

# DEV ENVIRONMENT

# CLUSTER_NAME=crowd-dev
# SERVICE_NAME=crowd-dev-app2-Service-FJM8LRJNL7HN

# TEST ENVIRONMENT

# CLUSTER_NAME=crowd-test2
# SERVICE_NAME=crowd-test2-app-Service-FKAYXTF9E7SW


# SEC ENVIRONMENT
 
 CLUSTER_NAME=concordia2
 SERVICE_NAME=crowd-isso-app-Service-1MO5VJL0CGDBM

# STAGE ENVIRONMENT

# ECS AutoScaling role ARN
# arn:aws:iam::351149051428:role/crowd-stage-ECS-BU57ZZJOQ-ECSServiceAutoScalingRol-1EK5KYLQQTVVU
# Load Balancer Listener
# arn:aws:elasticloadbalancing:us-east-1:351149051428:listener/app/crowd-stage/53c19bcd76f00cb2/3d0c172d811b4926
# CLUSTER_NAME=crowd-stage
# SERVICE_NAME=crowd-stage-app-Service-MYJFKU3PS5OM

# PROD ENVIRONMENT

# CLUSTER_NAME=crowd-prod
# SERVICE_NAME=crowd-prod-app-Service


AWS_REGION=us-east-1

export CLUSTER_NAME AWS_REGION SERVICE_NAME

aws ecs update-service --cluster $CLUSTER_NAME --service $SERVICE_NAME --force-new-deployment
