#!/usr/bin/env python3

import boto3
import requests
from botocore.exceptions import ClientError

SECURITY_GROUP_ID = "sg-0cf16b045e14f5fad"

ec2 = boto3.client("ec2")

ipv4_cidrs = requests.get("https://www.cloudflare.com/ips-v4").text.splitlines()
ipv6_cidrs = requests.get("https://www.cloudflare.com/ips-v6").text.splitlines()

request_payload = {
    "IpProtocol": "tcp",
    "FromPort": 443,
    "ToPort": 443,
    "IpRanges": [
        {"CidrIp": cidr, "Description": "CloudFlare IPv4"} for cidr in ipv4_cidrs
    ],
    "Ipv6Ranges": [
        {"CidrIpv6": cidrv6, "Description": "CloudFlare IPv6"} for cidrv6 in ipv6_cidrs
    ],
}

try:
    data = ec2.authorize_security_group_ingress(
        GroupId=SECURITY_GROUP_ID, IpPermissions=[request_payload]
    )
    print("Ingress Successfully Set %s" % data)
except ClientError as e:
    print(e)
