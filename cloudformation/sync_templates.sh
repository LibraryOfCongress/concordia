#!/bin/bash

set -eu

aws s3 sync . s3://crowd-deployment
