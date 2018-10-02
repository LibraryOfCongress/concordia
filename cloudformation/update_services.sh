#!/bin/bash

set -eu

# DEV ENVIRONMENT

# CLUSTER_NAME=crowd-dev
# SERVICE_NAME=crowd-dev-app-Service-GNP6S8RBB14T
# ECS AutoScaling role ARN
# arn:aws:iam::351149051428:role/crowd-dev-ECS-RQZSJ89GYY4-ECSServiceAutoScalingRol-KJ5SO8E1KIWF	
# Load Balancer Listener
# arn:aws:elasticloadbalancing:us-east-1:351149051428:listener/app/crowd-dev/8b148c019a172548/3744cde523a62f96	

# TEST ENVIRONMENT

# CLUSTER_NAME=crowd-test2
# SERVICE_NAME=crowd-test2-app-Service-FKAYXTF9E7SW
# ECS AutoScaling role ARN
# arn:aws:iam::351149051428:role/crowd-test2-ECS-1I34ZK7Z3-ECSServiceAutoScalingRol-U5GIQOZ1RQ8Z	
# Load Balancer Listener
# arn:aws:elasticloadbalancing:us-east-1:351149051428:listener/app/crowd-test2/3d7aa00aa454c0c7/1560db455f58ceb2	


# SEC ENVIRONMENT
 
# CLUSTER_NAME=concordia2
# SERVICE_NAME=crowd-isso-app-Service-1MO5VJL0CGDBM
# ECS AutoScaling role ARN
# arn:aws:iam::351149051428:role/concordia2-ECS-121WQ9X8QD-ECSServiceAutoScalingRol-P4BKQ062R74J
# Load Balancer Listener
# arn:aws:elasticloadbalancing:us-east-1:351149051428:listener/app/concordia2/f89ed8d66573aeb4/ee2446092143046f	

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

aws ecs update-service --region $AWS_REGION --cluster $CLUSTER_NAME --service $SERVICE_NAME --force-new-deployment
