#!/bin/bash

set -e -u # Exit immediately for unhandled errors or undefined variables

echo Running indexing
./manage.py search_index --rebuild -f
