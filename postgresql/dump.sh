#!/bin/bash

pg_dump -Fc --clean --create --no-owner --no-acl -U concordia -h $POSTGRES_HOST concordia > concordia.dmp