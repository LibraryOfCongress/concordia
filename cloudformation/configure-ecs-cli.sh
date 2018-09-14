
aws s3 sync . s3://rstorey-concordia-refarch

# Uses https://github.com/aws/amazon-ecs-cli

ecs-cli configure profile --profile-name concordia2 --access-key $AWS_ACCESS_KEY --secret-key $AWS_SECRET_KEY

ecs-cli configure --cluster concordia2 --default-launch-type FARGATE --region us-east-1 --config-name concordia2

# These following two steps only need to be done the first time the ECS cluster is configured and set up.
# aws iam --region us-east-1 create-role --role-name ecsTaskExecutionRole --assume-role-policy-document file://task-execution-assume-role.json
# aws iam --region us-east-1 attach-role-policy --role-name ecsTaskExecutionRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

ecs-cli compose --project-name concordia2 service up --create-log-groups --cluster-config concordia2
