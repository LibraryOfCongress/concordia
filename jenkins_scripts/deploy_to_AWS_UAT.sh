#!/usr/bin/expect

set timeout 60

spawn ssh -i "/var/lib/jenkins/.ssh/aws.pem" ubuntu@ec2-18-220-59-98.us-east-2.compute.amazonaws.com

expect "$ "

send -- "cd projects/concordia\r"
expect "$ "

send -- "./AWS_deploy_UAT.sh\r"
expect "$ "

sleep 660

send -- "exit\r"