#!/bin/bash

set -eu -o pipefail

AWS_ACCOUNT_ID="$(aws sts get-caller-identity  --output=text --query "Account")"
eval "$(aws ecr get-login --no-include-email --region us-east-1)"

docker build -t concordia/kibana-proxy .
docker tag concordia/kibana-proxy:latest "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/kibana-proxy:latest"
docker push "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/kibana-proxy:latest"
