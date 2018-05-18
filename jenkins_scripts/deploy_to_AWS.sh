#!/usr/bin/expect

set timeout 60

spawn ssh -i "/var/lib/jenkins/.ssh/aws.pem" ubuntu@ec2-18-191-56-17.us-east-2.compute.amazonaws.com

expect "$ "

send -- "cd projects/concordia\r"
expect "$ "

send -- "./AWS_deploy.sh\r"
expect "$ "

sleep 10

send -- "exit\r"

