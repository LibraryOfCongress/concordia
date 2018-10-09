#!/usr/bin/env python3

# TODO: move this into Ansible or at least use Boto

import json
import subprocess
import requests

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

json_payload = json.dumps([request_payload])

subprocess.check_call(
    [
        "aws",
        "ec2",
        "authorize-security-group-ingress",
        "--group-id",
        "sg-0e07161e54ca34212",
        "--ip-permissions",
        json_payload,
    ]
)
