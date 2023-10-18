import os

import boto3
from botocore.exceptions import ClientError

AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


def get_secret(secret_name):
    endpoint_url = "https://secretsmanager.%s.amazonaws.com" % AWS_DEFAULT_REGION
    region_name = AWS_DEFAULT_REGION
    secret = None

    session = boto3.session.Session()
    client = session.client(
        service_name="secretsmanager",
        region_name=region_name,
        endpoint_url=endpoint_url,
    )

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            raise Exception(
                "The requested secret " + secret_name + " was not found"
            ) from e
        elif e.response["Error"]["Code"] == "InvalidRequestException":
            raise Exception("The request was invalid due to:", e) from e
        elif e.response["Error"]["Code"] == "InvalidParameterException":
            raise Exception("The request had invalid params:", e) from e
    else:
        # Decrypted secret using the associated KMS CMK Depending on whether the
        # secret was a string or binary, one of these fields will be populated
        if "SecretString" in get_secret_value_response:
            secret = get_secret_value_response["SecretString"]
        else:
            secret = get_secret_value_response["SecretBinary"]

    return secret
