from locust import TaskSet, between
from locust.contrib.fasthttp import FastHttpUser


def campaigns_topics(user):
    user.client.get("/campaigns-topics/")


def about(user):
    user.client.get("/about/")


def index(user):
    user.client.get("/")


def resources(user):
    user.client.get("/resources/")


def herencia(user):
    user.client.get("/campaigns/herencia-centuries-of-spanish-legal-documents/")


def next_asset(user):
    user.client.get(
        "http://concordia.mshome.net:8000/campaigns/joseph-holt/next-transcribable-asset"
    )


class UserBehavior(TaskSet):
    tasks = {
        index: 2,
        about: 1,
        resources: 1,
        campaigns_topics: 3,
        herencia: 4,
        next_asset: 4,
    }


class WebsiteUser(FastHttpUser):
    tasks = [UserBehavior]
    wait_time = between(5.0, 9.0)
