#!/bin/bash

set -eu

AWS_ACCOUNT_ID="$(aws sts get-caller-identity  --output=text --query "Account")"

eval "$(aws ecr get-login --no-include-email --region us-east-1)"

cp -R $WORKSPACE/.git `pwd`

docker build -t concordia .
docker tag concordia:latest ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia:latest

docker build -t concordia/importer:latest --file importer/Dockerfile .
docker tag concordia/importer:latest ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/importer:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/importer:latest

# docker pull rabbitmq:latest
# docker tag rabbitmq:latest ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/rabbitmq:latest
# docker push ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/rabbitmq:latest

# aws ecs update-service --cluster concordia2 --service concordia-service --force-new-deployment