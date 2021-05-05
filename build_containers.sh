#!/bin/bash

set -eu -o pipefail

BUILD_ALL=${BUILD_ALL:=0}
BUILD_NUMBER=${BUILD_NUMBER:=1}
TAG=${TAG:-test}
PUBLISH_CONTAINERS=${PUBLISH_CONTAINERS:=1}

# Get an unique venv folder to use inside workspace
VENV=".venv-${BUILD_NUMBER}"

# Initialize new venv
python3 -m venv "${VENV}"
source "${VENV}/bin/activate"

# Update pip
pip3 install -U pip
pip3 install -U setuptools
pip3 install -U pipenv

pipenv install --dev --deploy

FULL_VERSION_NUMBER="$(python3 setup.py --version)"
VERSION_NUMBER=$(echo "${FULL_VERSION_NUMBER}" | cut -d '+' -f 1)

if [ $PUBLISH_CONTAINERS -eq 1 ]; then
    AWS_ACCOUNT_ID="$(aws sts get-caller-identity  --output=text --query "Account")"
    eval "$(aws ecr get-login --no-include-email --region us-east-1)"
fi

python3 setup.py build

docker build -t concordia .

if [ $PUBLISH_CONTAINERS -eq 1 ]; then
    docker tag concordia:latest "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia:${VERSION_NUMBER}"
    docker tag concordia:latest "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia:${TAG}"
    docker push "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia:${VERSION_NUMBER}"
    docker push "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia:${TAG}"
fi

if [ $BUILD_ALL -eq 1 ]; then

    docker build -t concordia/importer --file importer/Dockerfile .
    docker build -t concordia/celerybeat --file celerybeat/Dockerfile .

    if [ $PUBLISH_CONTAINERS -eq 1 ]; then
        docker tag concordia/importer:latest "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/importer:${VERSION_NUMBER}"
        docker tag concordia/importer:latest "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/importer:${TAG}"
        docker push "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/importer:${VERSION_NUMBER}"
        docker push "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/importer:${TAG}"

        docker tag concordia/celerybeat:latest "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/celerybeat:${VERSION_NUMBER}"
        docker tag concordia/celerybeat:latest "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/celerybeat:${TAG}"
        docker push "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/celerybeat:${VERSION_NUMBER}"
        docker push "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/concordia/celerybeat:${TAG}"
    fi
fi
