data "aws_caller_identity" "current" {}

data "aws_canonical_user_id" "current" {}

data "aws_region" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_iam_role" "execution_role" {
  name = "ecsTaskExecutionRole"
}
