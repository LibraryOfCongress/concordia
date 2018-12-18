#!/bin/bash

# For AMI: sudo yum -y install https://download.postgresql.org/pub/repos/yum/9.6/redhat/rhel-6-x86_64/pgdg-ami201503-96-9.6-2.noarch.rpm
#          sudo yum -y install postgresql96

pg_dump -Fc --clean --create --no-owner --no-acl -U concordia -h $POSTGRESQL_HOST concordia -f concordia.dmp