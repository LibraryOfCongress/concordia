FROM python:3.8-slim

## Add the wait script to the image
ADD https://github.com/ufoscout/docker-compose-wait/releases/download/2.2.1/wait /wait
RUN chmod +x /wait

ENV DEBIAN_FRONTEND="noninteractive"

RUN echo "deb http://deb.debian.org/debian buster-backports main" >> /etc/apt/sources.list.d/buster-backports.list

RUN apt-get update -qy && apt-get dist-upgrade -qy && apt-get install -o Dpkg::Options::='--force-confnew' -qy \
    git curl \
    libmemcached-dev \
    # Pillow/Imaging: https://pillow.readthedocs.io/en/latest/installation.html#external-libraries
    libz-dev libfreetype6-dev \
    libtiff-dev libjpeg-dev libopenjp2-7-dev libwebp-dev zlib1g-dev \
    # Postgres client library to build psycopg2
    libpq-dev \
    locales \
    nodejs node-gyp && apt-get -qy -t buster-backports install npm && apt-get -qy autoremove && apt-get -qy autoclean

RUN locale-gen en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8

ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app

ENV DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-concordia.settings_docker}

RUN pip3 install pipenv

WORKDIR /app
COPY . /app

RUN npm install --silent --global npm@latest && /usr/local/bin/npm install --silent && npx gulp build

RUN pipenv install --system --dev --deploy && rm -rf ~/.cache/

EXPOSE 80

CMD /wait && /bin/bash entrypoint.sh
