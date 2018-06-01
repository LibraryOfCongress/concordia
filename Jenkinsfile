pipeline {
    agent any
    stages {
        stage('Clone') {
            steps {
                git 'https://github.com/LibraryOfCongress/concordia.git'
            }
        }
        stage('Test') {
            steps {
                sh 'python3 -m venv env'
                sh 'source ./env/bin/activate'
                sh 'pip3 install -r requirements_devel.txt'
                sh 'cd concordia'
                sh 'cp env-devel.ini_template env.ini'
                sh 'export PYTHONPATH=$PYTHONPATH:.'
                sh 'mkdir -p logs'
                sh 'touch logs/celery.log'
                sh 'docker-compose up -d db'
                sh 'docker-compose up -d rabbit'
                sh 'sleep 60'
                sh 'python3 -m pytest .'
            }
        }
        stage('Deploy') {
            steps {
                sh 'cp env.ini_template env.ini'
                sh 'docker-compose up -d'
            }
        }
    }
}