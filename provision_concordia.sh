#!/usr/bin/env bash

sudo add-apt-repository ppa:jonathonf/python-3.6
sudo apt-get update
sudo apt-get install python3.6
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
sudo python3 get-pip.py
sudo pip install -U pip
sudo pip install virtualenv
mkdir concordia
cd concordia
virtualenv ENV
source ENV/bin/activate
pip install Django
