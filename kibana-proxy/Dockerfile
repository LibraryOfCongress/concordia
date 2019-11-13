FROM ubuntu:latest

RUN apt-get update
RUN apt-get install -y wget

RUN wget https://github.com/abutaha/aws-es-proxy/releases/download/v0.9/aws-es-proxy-0.9-linux-386

RUN chmod u+x /aws-es-proxy-0.9-linux-386

ENV AWS_ES_PROXY_ARGS=${AWS_ES_PROXY_ARGS:-}

EXPOSE 80
CMD /aws-es-proxy-0.9-linux-386 -endpoint "${ELASTICSEARCH_ENDPOINT}" -no-sign-reqs -listen 0.0.0.0:80 "${AWS_ES_PROXY_ARGS}"
