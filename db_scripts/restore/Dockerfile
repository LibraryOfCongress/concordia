FROM git.loc.gov:4567/devops/docker-hub-mirror/amazonlinux:2
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
