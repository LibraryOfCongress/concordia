#!/bin/bash

aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 619333082511.dkr.ecr.us-east-1.amazonaws.com
docker build --platform linux/amd64 --no-cache --pull -t crowd-db-dump .
docker tag crowd-db-dump:latest 619333082511.dkr.ecr.us-east-1.amazonaws.com/crowd-db-dump:latest
docker push 619333082511.dkr.ecr.us-east-1.amazonaws.com/crowd-db-dump:latest
