FROM alpine:latest

RUN apk update
RUN apk add --no-cache nginx wget openrc

# RUN yum update -y && amazon-linux-extras install -y nginx && yum install -y wget

RUN wget https://github.com/abutaha/aws-es-proxy/releases/download/v0.9/aws-es-proxy-0.9-linux-386

RUN mv /etc/nginx/nginx.conf /etc/nginx/nginx.conf.save

ADD nginx.conf /etc/nginx/

RUN rc-update add nginx default

EXPOSE 80
ENTRYPOINT ["/aws-es-proxy-0.9-linux-386 -endpoint ${ELASTICSEARCH_ENDPOINT} -no-sign-reqs -listen 0.0.0.0:9200"]
