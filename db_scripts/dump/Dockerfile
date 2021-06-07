FROM git.loc.gov:4567/devops/docker-hub-mirror/amazonlinux:2
SHELL ["bin/bash", "-c"]
RUN echo $' \n\
[pgdg12] \n\
name=PostgreSQL 12 for RHEL/CentOS 7 - x86_64 \n\
baseurl=https://download.postgresql.org/pub/repos/yum/12/redhat/rhel-7-x86_64 \n\
enabled=1 \n\
gpgcheck=0' >> /etc/yum.repos.d/pgdg.repo

RUN yum makecache && yum -y install postgresql12 \
    && yum update -y \
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
COPY dump.sh .
CMD ["./dump.sh"]
