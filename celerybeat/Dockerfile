FROM ubuntu:18.04

ENV DEBIAN_FRONTEND="noninteractive"

# Pillow/Imaging: https://pillow.readthedocs.io/en/latest/installation.html#external-libraries
RUN apt-get update -qy && apt-get dist-upgrade -qy && apt-get install -o Dpkg::Options::='--force-confnew' -qy \
    git curl \
    python3.6 python3.6-dev python3-pip \
    libz-dev libfreetype6-dev \
    libmemcached-dev \
    libtiff-dev libjpeg-dev libopenjp2-7-dev libwebp-dev zlib1g-dev \
    graphviz \
    locales && apt-get -qy autoremove && apt-get -qy autoclean

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

RUN pipenv install --system --dev --deploy

CMD [ "/bin/bash", "celerybeat/entrypoint.sh" ]
