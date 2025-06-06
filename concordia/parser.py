import defusedxml.ElementTree as ET
import requests


def fetch_blog_posts():
    url = "https://blogs.loc.gov/thesignal/feed/"
    response = requests.get(url, timeout=60)

    root = ET.fromstring(response.content)
    channel = root.find("channel")
    items = channel.findall("item")
    feed_items = [
        {
            "title": item.find("title").text,
            "link": item.find("link").text,
            "description": item.find("description").text,
        }
        for item in items[:18]
    ]

    return feed_items
