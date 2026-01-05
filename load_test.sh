#!/bin/bash
set -euo pipefail

LOCUST_USERS="${LOCUST_USERS:-100}"
LOCUST_SPAWN_RATE="${LOCUST_SPAWN_RATE:-2}"
LOCUST_RUN_TIME="${LOCUST_RUN_TIME:-1m30s}"
LOCUST_HOST="${LOCUST_HOST:-https://crowd-dev.loc.gov}"

exec locust \
  --headless \
  -u "${LOCUST_USERS}" \
  -r "${LOCUST_SPAWN_RATE}" \
  --run-time "${LOCUST_RUN_TIME}" \
  --host "${LOCUST_HOST}"
