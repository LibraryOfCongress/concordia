FROM ubuntu:18.04

ENV DEBIAN_FRONTEND="noninteractive"

# Pillow/Imaging: https://pillow.readthedocs.io/en/latest/installation.html#external-libraries
RUN apt-get update -qy && apt-get install -o Dpkg::Options::='--force-confnew' -qy \
    git curl \
    python3 python3-dev python3-pip \
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
ENV DJANGO_SETTINGS_MODULE=concordia.settings_prod

RUN pip3 install pipenv

COPY vendor /vendor
WORKDIR /app
COPY . /app
RUN pipenv install --system --dev --deploy

EXPOSE 80
# CMD [ "/bin/bash", "entrypoint.sh" ]
## Add the wait script to the image
ADD https://github.com/ufoscout/docker-compose-wait/releases/download/2.2.1/wait /wait
RUN chmod +x /wait

CMD /wait && /bin/bash entrypoint.sh
