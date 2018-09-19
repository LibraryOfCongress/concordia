#!/bin/bash

set -eu

aws ecs register-task-definition --cli-input-json file://task_definitions.json

# aws ecs update-service --cluster concordia2 --service concordia-importer --force-new-deployment

# aws ecs update-service --cluster concordia2 --service concordia2-ConcordiaService-10B18QIYZSVWY-Service-KQ4BOX48UYXS --force-new-deployment
