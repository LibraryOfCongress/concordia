#!/bin/bash

locust  --headless -u 100 -r 2 --run-time 1m30s --host http://c2vldjsteg01.loctest.gov
