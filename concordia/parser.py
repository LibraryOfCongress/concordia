import html
from html.parser import HTMLParser

import defusedxml.ElementTree as ET
import requests


class OGImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.og_image = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "meta":
            attr_dict = dict(attrs)
            print(attr_dict)
            if attr_dict.get("property") == "og:image" and "content" in attr_dict:
                self.og_image = attr_dict["content"]


def extract_og_image(url):
    """Fetch the meta value from the HTML."""
    try:
        response = requests.get(url, timeout=5)
        parser = OGImageParser()
        parser.feed(html.unescape(response.text))
        return parser.og_image
    except requests.RequestException:
        return None


def fetch_blog_posts():
    """get and parse The Signal's RSS feed"""
    try:
        response = requests.get("https://blogs.loc.gov/thesignal/feed/", timeout=60)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception:
        return []

    items = root.find("channel").findall("item")
    feed_items = []
    for item in items[:18]:
        feed_item = {
            "title": item.find("title").text,
            "description": item.find("description").text,
        }
        link = item.find("link")
        if link is not None:
            feed_item["link"] = link.text
            og_image = extract_og_image(link)
            if og_image is not None:
                feed_item["og:image"] = og_image
        feed_items.append(feed_item)

    return feed_items
