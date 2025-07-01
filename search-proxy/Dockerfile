FROM ubuntu:latest

RUN apt-get update
RUN apt-get install -y wget curl

# Ensure that the Library's certificate authority is trusted so the tampering
# proxy will not break TLS validation. See
# https://staff.loc.gov/wikis/display/SE/Configuring+HTTPS+clients+for+the+HTTPS+tampering+proxy.
RUN curl -fso /etc/ssl/certs/LOC-ROOT-CA-1.crt http://crl.loc.gov/LOC-ROOT-CA-1.crt && openssl x509 -inform der -in /etc/ssl/certs/LOC-ROOT-CA-1.crt -outform pem -out /etc/ssl/certs/LOC-ROOT-CA-1.pem && c_rehash

RUN wget https://github.com/abutaha/aws-es-proxy/releases/download/v1.5/aws-es-proxy-1.5-linux-amd64

RUN chmod u+x /aws-es-proxy-1.5-linux-amd64

ENV AWS_ES_PROXY_ARGS=${AWS_ES_PROXY_ARGS:-}

EXPOSE 80
CMD /aws-es-proxy-1.5-linux-amd64 -endpoint "${OPENSEARCH_ENDPOINT}" -no-sign-reqs -listen 0.0.0.0:80 "${AWS_ES_PROXY_ARGS}" --verbose
