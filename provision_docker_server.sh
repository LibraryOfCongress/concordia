sudo apt-get remove docker docker-engine docker.io
sudo apt-get update -qy
sudo apt-get install -qy -o Dpkg::Options::='--force-confnew' \
    apt-transport-https \
    ca-certificates \
    curl \
    software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository \
   "deb [arch=amd64] https://download.docker.com/linux/ubuntu \
   $(lsb_release -cs) \
   stable"
sudo apt-get update -qy
sudo apt-get install -qy -o Dpkg::Options::='--force-confnew' docker-ce

sudo sysctl -w vm.max_map_count=262144

 # Get latest version of docker-compose
sudo curl -L https://github.com/docker/compose/releases/download/1.22.0/docker-compose-$(uname -s)-$(uname -m) -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

git clone https://github.com/LibraryOfCongress/concordia.git
cd concordia
cp example_env_file .env
sudo /usr/local/bin/docker-compose up -d