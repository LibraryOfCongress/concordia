# Base runtime: Debian 12 (bookworm) slim + Python 3.12.
FROM python:3.12-slim-bookworm

# Major Node.js version to install (e.g., 20, 22). This is used to select the
# NodeSource APT repository "node_<major>.x".
ARG NODE_MAJOR=20

# Include a small "wait for dependencies" helper used by the container command.
# This is downloaded at build time and placed at /wait.
## Add the wait script to the image
ADD https://github.com/ufoscout/docker-compose-wait/releases/download/2.2.1/wait /wait
RUN chmod +x /wait

# Prevent interactive prompts during apt operations.
ENV DEBIAN_FRONTEND="noninteractive"

# Bootstrap minimal tooling needed later in the build:
# - curl: download files/keys
# - ca-certificates: validate HTTPS endpoints
# - gnupg: import and dearmor APT repository signing keys
RUN apt-get update -qy && apt-get install -qy curl ca-certificates gnupg

# Trust the Library's certificate authority so the HTTPS tampering proxy does
# not break TLS validation for clients inside the container.
#
# This downloads the CA certificate, converts it to PEM, and refreshes the
# OpenSSL certificate hashes so it is recognized by OpenSSL-based clients.
# Ensure that the Library's certificate authority is trusted so the tampering
# proxy will not break TLS validation. See
# https://staff.loc.gov/wikis/display/SE/Configuring+HTTPS+clients+for+the+HTTPS+tampering+proxy.
RUN curl -fso /etc/ssl/certs/LOC-ROOT-CA-1.crt http://crl.loc.gov/LOC-ROOT-CA-1.crt && openssl x509 -inform der -in /etc/ssl/certs/LOC-ROOT-CA-1.crt -outform pem -out /etc/ssl/certs/LOC-ROOT-CA-1.pem && c_rehash

# Install Node.js via the NodeSource APT repository (manual setup; no setup
# script). Debian bookworm ships Node 18; adding this repo allows installing a
# newer major version (e.g., Node 20) via apt.
#
# This step:
# - creates a dedicated keyring directory under /etc/apt/keyrings
# - downloads and installs the NodeSource signing key into a keyring file
# - registers the NodeSource repository for the selected Node.js major line
#
# Note: When installing Node.js from NodeSource, the `nodejs` package includes
# npm, so there is no separate `npm` APT package to install here.
#
# References: NodeSource "Repository Manual Installation" guide. https://github.com/nodesource/distributions/wiki/Repository-Manual-Installation
RUN \
    # Create a dedicated directory for third-party APT keyrings.
    mkdir -p /etc/apt/keyrings && \
    # Download the NodeSource repository signing key and store it as a keyring
    # file that apt can use to verify NodeSource packages.
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    # Register the NodeSource repository for the selected Node.js major version.
    # The "signed-by=" option scopes trust to just this repository entry.
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list

# Bring the base OS packages fully up to date, then install system dependencies
# needed to build and run the application.
#
# Notes:
# - dist-upgrade pulls in security and point-release updates for the base image.
# - --force-confnew ensures updated config files are accepted when prompted.
# - autoremove/autoclean reduce image size after installing packages.
RUN apt-get update -qy && apt-get dist-upgrade -qy && apt-get install -o Dpkg::Options::='--force-confnew' -qy \
    git \
    libmemcached-dev \
    # Pillow/Imaging: https://pillow.readthedocs.io/en/latest/installation.html#external-libraries
    libz-dev libfreetype6-dev \
    libtiff-dev libjpeg-dev libopenjp2-7-dev libwebp-dev zlib1g-dev \
    # Postgres client library to build psycopg
    libpq-dev \
    locales \
    # Weasyprint requirements
    libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 \
    # Tesseract
    tesseract-ocr tesseract-ocr-all \
    # Node.js runtime (from NodeSource) and build tooling for native addons.
    nodejs node-gyp && apt-get -qy autoremove && apt-get -qy autoclean

# Generate and configure a UTF-8 locale for consistent string handling.
RUN locale-gen en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8

# Python runtime settings:
# - unbuffered output for log visibility in containers
# - add /app to PYTHONPATH for module resolution
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app

# Default Django settings module for container runtime (can be overridden).
ENV DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-concordia.settings_docker}

# Ensure an up-to-date pip and install pipenv for dependency management.
RUN pip install --upgrade pip
RUN pip install --no-cache-dir pipenv

# Copy application code into the image.
WORKDIR /app
COPY . /app

# Front-end build and asset pipeline:
# - update npm to a known major version
# - install JS dependencies (production-only) and build assets via gulp
RUN npm install --silent --global npm@10 && /usr/local/bin/npm install --silent --omit=dev && npx gulp build
# Additional JS build step (kept as-is).
RUN npm run build

# Install Python dependencies into the system environment using Pipenv and
# remove Pipenv cache to reduce image size.
RUN pipenv install --system --dev --deploy && rm -rf ~/.cache/

# Container listens on port 80.
EXPOSE 80

# Wait for dependencies (via /wait) and then run the application entrypoint.
CMD /wait && /bin/bash entrypoint.sh
