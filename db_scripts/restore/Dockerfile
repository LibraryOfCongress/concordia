FROM git.loc.gov:4567/devops/docker-hub-mirror/amazonlinux:2
RUN yum update -y && amazon-linux-extras install -y postgresql9.6
COPY restore.sh .
CMD ["./restore.sh"]
