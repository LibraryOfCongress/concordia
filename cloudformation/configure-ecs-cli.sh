#!/bin/bash

set -eu

CLUSTER_NAME=crowd-dev
AWS_REGION=us-east-1

export CLUSTER_NAME AWS_REGION

# Uses https://github.com/aws/amazon-ecs-cli

ecs-cli configure --cluster $CLUSTER_NAME --default-launch-type FARGATE --region $AWS_REGION --config-name $CLUSTER_NAME

# These following two steps only need to be done the first time the ECS cluster is configured and set up.
aws iam --region $AWS_REGION create-role --role-name ecsTaskExecutionRole --assume-role-policy-document file://task-execution-assume-role.json
aws iam --region $AWS_REGION attach-role-policy --role-name ecsTaskExecutionRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
