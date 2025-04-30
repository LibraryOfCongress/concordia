#!/bin/bash

set -eu -o pipefail

AWS_ACCOUNT_ID="$(aws sts get-caller-identity  --output=text --query "Account")"
# Login to ECR - if you are using docker instead of podman - change to docker
aws ecr get-login --no-include-email --region us-east-1 | podman login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com"

podman build --no-cache --pull -t concordia/search-proxy .
podman tag concordia/search-proxy:latest "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/search-proxy:latest-amd64"
podman push "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/search-proxy:latest-amd64"
