import html
import logging
from html.parser import HTMLParser

import defusedxml.ElementTree as ET
import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)


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
    cache_key = f"og_image:{url}"

    try:
        response = requests.get(url, timeout=5)
        parser = OGImageParser()
        parser.feed(html.unescape(response.text))
        cache.set(cache_key, parser.og_image, timeout=24 * 60 * 60)
        return parser.og_image
    except requests.RequestException as e:
        logger.warning(
            "Failed to fetch image for blog post: %s",
            e,
            exc_info=True,
        )


def get_og_image(url):
    """Fetch the meta value from the HTML."""
    cache_key = f"og_image:{url}"
    cached_image = cache.get(cache_key)
    if cached_image is not None:
        return cached_image
    else:
        return extract_og_image(url)


def fetch_blog_posts():
    """get and parse The Signal's RSS feed"""
    try:
        response = requests.get(
            "https://blogs.loc.gov/thesignal/category/by-the-people-transcription-program/feed/",
            timeout=60,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except requests.exceptions.HTTPError as e:
        logger.warning(
            "HTTP error when fetching blog posts, but handled: %s",
            e,
            exc_info=True,
        )
        return []
    except requests.exceptions.ConnectionError as e:
        logger.warning(
            "Connection error when fetching blog posts: %s",
            e,
            exc_info=True,
        )
        return []
    except requests.exceptions.Timeout as e:
        logger.warning(
            "Timeout when fetching blog posts: %s",
            e,
            exc_info=True,
        )
        return []
    except requests.exceptions.RequestException as e:
        logger.warning(
            "Request exception when fetching blog posts: %s",
            e,
            exc_info=True,
        )
        return []

    return root.find("channel").findall("item")


def paginate_blog_posts():
    feed_items = []
    items = fetch_blog_posts()
    for item in items[:6]:
        feed_item = {
            "title": item.find("title").text,
        }
        link = item.find("link")
        if link is not None:
            feed_item["link"] = link.text
            og_image = get_og_image(link.text)
            if og_image is not None:
                feed_item["og_image"] = og_image
        feed_items.append(feed_item)
    segmented_items = [feed_items[:3]]
    if len(feed_items) > 3:
        segmented_items.append(feed_items[3:6])

    return segmented_items
