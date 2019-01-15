#!/bin/bash

export ENV_NAME=${ENV_NAME:-dev}

aws cloudformation create-stack --stack-name "${ENV_NAME}-bastionhosts"  --template-url https://s3.amazonaws.com/crowd-deployment/infrastructure/bastion-hosts.yaml --parameters "ParameterKey=EnvironmentName,ParameterValue=${ENV_NAME}" ParameterKey=KeyPairName,ParameterValue=rstorey@loc.gov