# This script creates a package to deploy to AWS.
# It is meant to be run one directory level above the project folder.

tar --exclude="concordia/__pycache__" --exclude="concordia/concordia.egg-info" --exclude="concordia/.*" -zcvf concordia.tar.gz concordia