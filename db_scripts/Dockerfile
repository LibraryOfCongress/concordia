# Base layer with all tools
FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal as base

# Trusted CA for proxy
RUN curl -fsO --output-dir /etc/pki/ca-trust/source/anchors/ http://crl.loc.gov/LOC-ROOT-CA-1.crt \
    && update-ca-trust

# Install tools once
RUN dnf -y upgrade && \
    dnf -y install postgresql15.x86_64 awscli-2.noarch && \
    dnf -y clean all

# Logic for Dump
FROM base as dump
COPY dump.sh .
RUN chmod +x dump.sh
CMD ["./dump.sh"] [cite: 3]

# Logic for Restore
FROM base as restore
COPY restore.sh .
RUN chmod +x restore.sh
CMD ["./restore.sh"]
