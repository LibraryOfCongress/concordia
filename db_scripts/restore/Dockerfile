FROM public.ecr.aws/amazonlinux/amazonlinux:2

# Ensure that the Library's certificate authority is trusted so the tampering
# proxy will not break TLS validation. See
# https://staff.loc.gov/wikis/display/SE/Configuring+HTTPS+clients+for+the+HTTPS+tampering+proxy.
RUN curl -fsO --output-dir /etc/pki/ca-trust/source/anchors/ http://crl.loc.gov/LOC-ROOT-CA-1.crt && update-ca-trust

RUN yum update -y && amazon-linux-extras install -y postgresql12 \
    && yum -y install unzip \
    && curl -sL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip \
    && unzip awscliv2.zip \
    && aws/install \
    && rm -rf \
    awscliv2.zip \
    aws \
    /usr/local/aws-cli/v2/*/dist/aws_completer \
    /usr/local/aws-cli/v2/*/dist/awscli/data/ac.index \
    /usr/local/aws-cli/v2/*/dist/awscli/examples
COPY restore.sh .
CMD ["./restore.sh"]
