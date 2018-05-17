#!/usr/bin/expect

set timeout 60

spawn ssh -i "/var/lib/jenkins/.ssh/aws.pem" ubuntu@ec2-18-191-56-17.us-east-2.compute.amazonaws.com

expect "$ "

send -- "cd projects/concordia\r"
expect "$ "

send -- "./AWS_deploy.sh\r"
expect "$ "

<<<<<<< HEAD
sleep 400
=======
send -- "/usr/bin/sudo pkill docker-compose\r"
expect "$ "

sleep 10

send -- "/usr/bin/sudo /usr/bin/docker rm $(/usr/bin/sudo /usr/bin/docker kill $(/usr/bin/sudo /usr/bin/docker ps -aq))\r"
expect "$ "

send -- "/usr/bin/sudo /usr/bin/docker rmi -f $(/usr/bin/sudo /usr/bin/docker images -q)\r"
expect "$ "

send -- "/usr/bin/sudo /usr/bin/docker container prune -f\r"
expect "$ "
>>>>>>> Added full path to docker commands

send -- "/usr/bin/sudo /usr/bin/docker exec -it concordia_app_1 bash -c \"./migrate_and_user.sh && exit\"\r"
expect "$ "

sleep 5

send -- "exit\r"

