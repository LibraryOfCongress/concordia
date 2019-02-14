FROM ubuntu:18.04

ENV DEBIAN_FRONTEND="noninteractive"

RUN apt-get update -qy && apt-get install -o Dpkg::Options::='--force-confnew' -qy \
    git curl \
    libmemcached-dev \
    python3.6 python3.6-dev python3-pip \
    libz-dev libfreetype6-dev \
    libtiff-dev libjpeg-dev libopenjp2-7-dev libwebp-dev zlib1g-dev \
    graphviz \
    locales

RUN locale-gen en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8

ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app

ENV DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-concordia.settings_docker}

ENV ELASTICSEARCH_DSL_AUTOSYNC=True

RUN pip3 install pipenv

WORKDIR /app
COPY . /app

RUN pipenv install --system --dev --deploy

CMD /bin/bash indexer/entrypoint.sh
