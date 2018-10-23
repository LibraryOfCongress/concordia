wget -q -O - https://pkg.jenkins.io/debian/jenkins.io.key | sudo apt-key add -
sudo sh -c 'echo deb http://pkg.jenkins.io/debian-stable binary/ > /etc/apt/sources.list.d/jenkins.list'
sudo apt-get update
sudo apt-get install -qy -o Dpkg::Options::='--force-confnew' default-jre jenkins
sudo usermod -aG docker jenkins
sudo apt-get install -qy -o Dpkg::Options::='--force-confnew' \
    python3 python3-dev python3-venv python3-pip \
    libtiff-dev libjpeg-dev libopenjp2-7-dev libwebp-dev zlib1g-dev \
    graphviz
sudo service start jenkins