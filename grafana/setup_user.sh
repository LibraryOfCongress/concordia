#!/bin/bash

grafana-cli admin reset-admin-password --homepath "/usr/share/grafana" $GRAFANA_ADMIN_PW
