#!/bin/bash

# Elastic won't start unless this system param is increased

sysctl -w vm.max_map_count=262144
