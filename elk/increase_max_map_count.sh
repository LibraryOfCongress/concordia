#!/bin/bash

# Elastic won't start unless this system param is increased
# See https://www.elastic.co/guide/en/elasticsearch/reference/current/docker.html

sysctl -w vm.max_map_count=262144
