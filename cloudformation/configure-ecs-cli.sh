
aws s3 sync . s3://rstorey-concordia-refarch

# Uses https://github.com/aws/amazon-ecs-cli

ecs-cli configure profile --profile-name concordia2 --access-key $AWS_ACCESS_KEY --secret-key $AWS_SECRET_KEY

ecs-cli configure --cluster concordia2 --default-launch-type FARGATE --region us-east-1 --config-name concordia2

# These following two steps only need to be done the first time the ECS cluster is configured and set up.
# aws iam --region us-east-1 create-role --role-name ecsTaskExecutionRole --assume-role-policy-document file://task-execution-assume-role.json
# aws iam --region us-east-1 attach-role-policy --role-name ecsTaskExecutionRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

$(aws ecr get-login --no-include-email --region us-east-1)

# Before you build the docker image, create an .env file as directed in the README.
# You'll need to disable elk in the app and comment out a couple lines from entrypoint.sh.

docker build -t concordia:latest .

docker build -t concordia/importer:latest --file importer/Dockerfile .

docker tag concordia:latest 351149051428.dkr.ecr.us-east-1.amazonaws.com/concordia:latest
docker tag concordia/importer:latest 351149051428.dkr.ecr.us-east-1.amazonaws.com/concordia/importer:latest

docker push 351149051428.dkr.ecr.us-east-1.amazonaws.com/concordia:latest
docker push 351149051428.dkr.ecr.us-east-1.amazonaws.com/concordia/importer:latest

# Doesn't work and isn't necessary...
# ecs-cli compose --file docker-compose-aws.yml --ecs-params ecs-params.yaml --project-name concordia create 

aws ecs register-task-definition --cli-input-json file://cloudformation/services/task_definitions.json  

ecs-cli compose --project-name concordia2 service up --create-log-groups --cluster-config concordia2
