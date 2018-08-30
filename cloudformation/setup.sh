# export AWS_ACCESS_KEY=""
# export AWS_SECRET_KEY=""
# export AWS_CREDENTIAL_FILE=""

# Make sure your aws credentials are configured before attempting to run this script.

S3_BUCKET_NAME = "rstorey-concordia-refarch"
STACK_NAME = "rstorey-refarch-test"

aws s3api create-bucket --bucket $S3_BUCKET_NAME --region us-east-1

aws s3 sync . s3://$S3_BUCKET_NAME

aws cloudformation create-stack --stack-name $STACK_NAME --template-url https://s3.amazonaws.com/$S3_BUCKET_NAME/master.yaml