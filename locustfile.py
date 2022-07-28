from locust import TaskSet, between
from locust.contrib.fasthttp import FastHttpLocust


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


def suffrage_next_asset(user):
    user.client.get(
        "/topics/suffrage-women-fight-for-the-vote/next-transcribable-asset/"
    )


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
