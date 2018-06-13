#!/usr/bin/expect

set timeout -1

spawn ssh -i "/var/lib/jenkins/.ssh/Artemis_UAT.pem" ubuntu@13.58.196.90

expect "$ "

send -- "cd projects/concordia\r"
expect "$ "

send -- "./AWS_deploy_UAT.sh\r"
expect "$ "

sleep 660

send -- "exit\r"