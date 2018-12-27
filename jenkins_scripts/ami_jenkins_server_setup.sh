sudo wget -O /etc/yum.repos.d/jenkins.repo http://pkg.jenkins-ci.org/redhat/jenkins.repo
sudo rpm --import https://jenkins-ci.org/redhat/jenkins-ci.org.key
sudo yum install -y jenkins java git docker python3 python3-pip \
    python3-devel libmemcached gcc libmemcached-devel zlib-devel
sudo usermod -aG docker jenkins
sudo service docker start
sudo chkconfig docker on
sudo service jenkins start
sudo chkconfig jenkins on
sudo cat /var/lib/jenkins/secrets/initialAdminPassword
# complete the web setup in browser at server:8080