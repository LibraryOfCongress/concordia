ecs-cli configure profile --profile-name concordia --access-key $AWS_ACCESS_KEY_ID --secret-key $AWS_SECRET_ACCESS_KEY

ecs-cli configure --cluster concordia --default-launch-type FARGATE --region us-east-2 --config-name concordia

aws iam --region us-east-2 create-role --role-name ecsTaskExecutionRole --assume-role-policy-document file://task-execution-assume-role.json

aws iam --region us-east-2 attach-role-policy --role-name ecsTaskExecutionRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

ecs-cli compose --project-name concordia service up --create-log-groups --cluster-config concordia

docker build -t concordia_app:latest .

docker build -t concordia_importer:latest --file importer/Dockerfile .

ecs-cli compose --file docker-compose.yml --ecs-params ecs-params.yaml --project-name concordia create 

aws ecs register-task-definition --cli-input-json file://cloudformation/services/task_definitions.json  