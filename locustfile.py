from locust import TaskSet, between
from locust.contrib.fasthttp import FastHttpLocust


def campaigns_topics(l):
    l.client.get("/campaigns-topics")


def about(l):
    l.client.get("/about")


def index(l):
    l.client.get("/")


def resources(l):
    l.client.get("/resources")


def herencia(l):
    l.client.get("/campaigns/herencia-centuries-of-spanish-legal-documents/")


def suffrage_next_asset(l):
    l.client.get("/topics/suffrage-women-fight-for-the-vote/next-transcribable-asset/")


class UserBehavior(TaskSet):
    tasks = {
        index: 2,
        about: 1,
        resources: 1,
        campaigns_topics: 3,
        herencia: 4,
        suffrage_next_asset: 4,
    }


class WebsiteUser(FastHttpLocust):
    task_set = UserBehavior
    wait_time = between(5.0, 9.0)
