#!/bin/bash
set -x 
/usr/bin/git pull origin > git_pull_results

/usr/bin/sudo pkill docker-compose

sleep 30

/usr/bin/sudo /usr/bin/docker rmi -f $(/usr/bin/sudo /usr/bin/docker images -q)

/usr/bin/sudo /usr/bin/docker container prune -f

/usr/bin/sudo nohup docker-compose up &

sleep 300

sudo docker exec -it concordia_app_1 bash -c "./migrate_and_user.sh && exit"

