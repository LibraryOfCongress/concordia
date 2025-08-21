#!/bin/bash

locust  --headless -u 100 -r 2 --run-time 1m30s --host https://crowd-dev.loc.gov
