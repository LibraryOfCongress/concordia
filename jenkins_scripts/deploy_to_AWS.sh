#!/usr/bin/expect

set timeout -1

spawn ssh -i "/var/lib/jenkins/.ssh/CHC_Test.pem" ubuntu@18.221.19.253

expect "$ "

send -- "cd projects/concordia\r"
expect "$ "

send -- "/usr/bin/sudo ./elk/increase_max_map_count.sh\r"
expect "$ "

send -- "./AWS_deploy.sh\r"
expect "$ "

sleep 200

send -- "/usr/bin/sudo /usr/bin/docker exec -it concordia_grafana bash -c \"./setup.sh/grafana_post_run.sh && exit\"\r"
expect "$ "

sleep 5

send -- "exit\r"

