FROM ubuntu:18.04

ENV PYTHONUNBUFFERED 1

# Pillow/Imaging: https://pillow.readthedocs.io/en/latest/installation.html#external-libraries
RUN apt-get update && apt-get install -y \
    git curl \
    python3 python3-dev python3-pip \
    libtiff-dev libjpeg-dev libopenjp2-7-dev libwebp-dev zlib1g-dev

WORKDIR /app
COPY . .
RUN pip3 install -e .
RUN pip3 install -r requirements/devel.pip

EXPOSE 80
ENTRYPOINT [ "/bin/bash", "entrypoint.sh" ]
