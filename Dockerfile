FROM python:3.12-slim-bookworm

## Add the wait script to the image
ADD https://github.com/ufoscout/docker-compose-wait/releases/download/2.2.1/wait /wait
RUN chmod +x /wait

ENV DEBIAN_FRONTEND="noninteractive"

RUN apt-get update -qy && apt-get install -qy curl

# Ensure that the Library's certificate authority is trusted so the tampering
# proxy will not break TLS validation. See
# https://staff.loc.gov/wikis/display/SE/Configuring+HTTPS+clients+for+the+HTTPS+tampering+proxy.

RUN curl -fso /etc/ssl/certs/LOC-ROOT-CA-1.crt http://crl.loc.gov/LOC-ROOT-CA-1.crt && openssl x509 -inform der -in /etc/ssl/certs/LOC-ROOT-CA-1.crt -outform pem -out /etc/ssl/certs/LOC-ROOT-CA-1.pem && c_rehash

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
    nodejs node-gyp npm && apt-get -qy autoremove && apt-get -qy autoclean

RUN locale-gen en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8

ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app

ENV DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-concordia.settings_docker}

RUN pip install --upgrade pip
RUN pip install --no-cache-dir pipenv

WORKDIR /app
COPY . /app

RUN npm install --silent --global npm@10 && /usr/local/bin/npm install --silent --omit=dev && npx gulp build
RUN npm run build

RUN pipenv install --system --dev --deploy && rm -rf ~/.cache/

EXPOSE 80

CMD /wait && /bin/bash entrypoint.sh
