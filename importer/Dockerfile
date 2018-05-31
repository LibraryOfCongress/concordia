FROM ubuntu:18.04

ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH=/app

# Pillow/Imaging: https://pillow.readthedocs.io/en/latest/installation.html#external-libraries
RUN apt-get update -qy && apt-get install -qy \
    git curl \
    python3 python3-dev python3-pip \
    libtiff-dev libjpeg-dev libopenjp2-7-dev libwebp-dev zlib1g-dev \
    graphviz \
    locales

RUN locale-gen en_US.UTF-8

COPY requirements.txt ./
COPY requirements_devel.txt ./
COPY requirements_importer.txt ./
ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8
COPY vendor /vendor
RUN pip3 install -r requirements_devel.txt

WORKDIR /app
COPY . .
RUN pip3 install --no-cache-dir -e .

CMD [ "/bin/bash", "importer/entrypoint.sh" ]
