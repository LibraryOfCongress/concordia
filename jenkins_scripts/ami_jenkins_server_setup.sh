sudo wget -O /etc/yum.repos.d/jenkins.repo http://pkg.jenkins-ci.org/redhat/jenkins.repo
sudo rpm --import https://jenkins-ci.org/redhat/jenkins-ci.org.key
sudo yum install jenkins
sudo yum install -y java git docker
sudo usermod -aG docker jenkins
sudo service docker start
sudo chkconfig docker on
sudo service jenkins start
sudo chkconfig jenkins on
sudo cat /var/lib/jenkins/secrets/initialAdminPassword


# complete the web setup in browser at server:8080


sudo curl -L https://github.com/docker/compose/releases/download/1.22.0/docker-compose-$(uname -s)-$(uname -m) -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

