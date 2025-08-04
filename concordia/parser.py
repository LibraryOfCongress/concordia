import html
from html.parser import HTMLParser

import defusedxml.ElementTree as ET
import requests
from django.core.cache import cache

from concordia.logging import ConcordiaLogger

structured_logger = ConcordiaLogger.get_logger(__name__)


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
    cached_image = cache.get(cache_key)
    if cached_image is not None:
        return cached_image

    try:
        response = requests.get(url, timeout=5)
        parser = OGImageParser()
        parser.feed(html.unescape(response.text))
        cache.set(cache_key, None, timeout=24 * 60 * 60)
        return parser.og_image
    except requests.RequestException:
        structured_logger.warning(
            "Failed to fetch image for blog post",
            reason="Image extract failed",
            reason_code="extract_og_image_failed",
        )


def fetch_blog_posts():
    """get and parse The Signal's RSS feed"""
    try:
        response = requests.get(
            "https://blogs.loc.gov/thesignal/category/by-the-people-transcription-program/feed/",
            timeout=60,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except requests.exceptions.HTTPError:
        structured_logger.warning(
            "HTTP Error: %s",
            event_code="fetch_blog_posts_failed",
            reason="HTTP error when fetching blog posts",
            reason_code="fetch_blog_http_error",
        )
        return []
    except requests.exceptions.ConnectionError:
        structured_logger.warning(
            "Error connecting to The Signal: %s",
            event_code="fetch_blog_posts_failed",
            reason="Connection error when fetching blog posts",
            reason_code="fetch_blog_connection_error",
        )
        return []
    except requests.exceptions.Timeout:
        structured_logger.warning(
            "Timeout Error: %s",
            event_code="fetch_blog_timed_out",
            reason="Timeout when fetching blog posts",
            reason_code="fetch_blog_timeout_error",
        )
        return []
    except requests.exceptions.RequestException:
        structured_logger.warning(
            "Error on request to The Signal: %s",
            event_code="fetch_blog_posts_failed",
            reason="Request exception when fetching blog posts",
            reason_code="fetch_blog_request_exception",
        )
        return []

    items = root.find("channel").findall("item")
    feed_items = []
    for item in items[:6]:
        feed_item = {
            "title": item.find("title").text,
        }
        link = item.find("link")
        if link is not None:
            feed_item["link"] = link.text
            og_image = extract_og_image(link.text)
            if og_image is not None:
                feed_item["og_image"] = og_image
        feed_items.append(feed_item)
    segmented_items = [feed_items[:3]]
    if len(feed_items) > 3:
        segmented_items.append(feed_items[3:6])

    return segmented_items
