#!/bin/bash
set -x
/usr/bin/git pull origin > git_pull_results

/usr/bin/sudo pkill docker-compose

sleep 30

/usr/bin/sudo nohup docker-compose build
/usr/bin/sudo nohup docker-compose up &

sleep 60