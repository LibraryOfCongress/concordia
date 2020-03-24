#!/bin/bash

locust  --no-web -c 1000 -r 100 --run-time 1h30m --host https://crowd-dev.loc.gov
