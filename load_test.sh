#!/bin/bash

locust  --headless -u 100 -r 10 --run-time 1m30s --host https://crowd-dev.loc.gov
