#!/usr/bin/env python3
"""
Ensure that every security group tagged with “AllowCloudFlareIngress” has
permissions for every public CloudFlare netblock
"""

import sys

import boto3
import requests
from botocore.exceptions import ClientError

EC2_CLIENT = boto3.client("ec2")

CLOUDFLARE_IPV4 = requests.get(
    "https://www.cloudflare.com/ips-v4", timeout=30
).text.splitlines()
CLOUDFLARE_IPV6 = requests.get(
    "https://www.cloudflare.com/ips-v6", timeout=30
).text.splitlines()


def add_ingess_rules_for_group(sg_id, existing_permissions):
    permissions = {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443}

    existing_ipv4 = set()
    existing_ipv6 = set()

    for existing in existing_permissions:
        if any(
            permissions[k] != existing[k] for k in ("IpProtocol", "FromPort", "ToPort")
        ):
            continue

        existing_ipv4.update(i["CidrIp"] for i in existing["IpRanges"])
        existing_ipv6.update(i["CidrIpv6"] for i in existing["Ipv6Ranges"])

    ipv4_ranges = [
        {"CidrIp": cidr, "Description": "CloudFlare"}
        for cidr in CLOUDFLARE_IPV4
        if cidr not in existing_ipv4
    ]
    ipv6_ranges = [
        {"CidrIpv6": cidr, "Description": "CloudFlare"}
        for cidr in CLOUDFLARE_IPV6
        if cidr not in existing_ipv6
    ]

    permissions["IpRanges"] = ipv4_ranges
    permissions["Ipv6Ranges"] = ipv6_ranges

    try:
        EC2_CLIENT.authorize_security_group_ingress(
            GroupId=sg_id, IpPermissions=[permissions]
        )
    except ClientError as exc:
        print(f"Unable to add permssions for {sg_id}: {exc}", file=sys.stderr)


def get_security_groups():
    paginator = EC2_CLIENT.get_paginator("describe_security_groups")
    page_iterator = paginator.paginate(
        Filters=[{"Name": "tag-key", "Values": ["AllowCloudFlareIngress"]}]
    )

    for page in page_iterator:
        for sg in page["SecurityGroups"]:
            yield sg["GroupId"], sg["IpPermissions"]


if __name__ == "__main__":
    for security_group_id, existing_permissions in get_security_groups():
        add_ingess_rules_for_group(security_group_id, existing_permissions)
