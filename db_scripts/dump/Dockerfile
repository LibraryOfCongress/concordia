FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal

# Ensure that the Library's certificate authority is trusted so the tampering
# proxy will not break TLS validation. See
# https://staff.loc.gov/wikis/display/SE/Configuring+HTTPS+clients+for+the+HTTPS+tampering+proxy.
RUN curl -fsO --output-dir /etc/pki/ca-trust/source/anchors/ http://crl.loc.gov/LOC-ROOT-CA-1.crt && update-ca-trust

RUN dnf -y upgrade && dnf -y install postgresql15.x86_64 awscli-2.noarch && dnf -y clean all
COPY dump.sh .
CMD ["./dump.sh"]
