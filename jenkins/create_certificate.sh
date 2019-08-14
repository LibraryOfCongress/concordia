#!/bin/bash
sudo mkdir -p /etc/pki/nginx/private
sudo openssl req -x509 -sha256 -newkey rsa:2048 -keyout /etc/pki/nginx/private/server.key -out /etc/pki/nginx/server.crt -days 1024 -nodes
