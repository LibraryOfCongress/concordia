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

    try:
        response = requests.get(url, timeout=5)
        parser = OGImageParser()
        parser.feed(html.unescape(response.text))
        cache.set(cache_key, parser.og_image, timeout=24 * 60 * 60)
        return parser.og_image
    except requests.RequestException:
        structured_logger.warning(
            "Failed to fetch image for blog post: %s",
            event_code="post_image_fetch_failed",
            reason=(
                "Failed to fetch Open Graph image from the "
                "given URL due to a network or HTTP error"
            ),
            reason_code="ogi_req_fail_fetch",
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
    except requests.exceptions.HTTPError:
        structured_logger.warning(
            "HTTP error when fetching blog posts, but handled: %s",
            event_code="handled_post_fetch_http_error",
            reason="The RSS feed returned an HTTP error response (e.g. 4xx or 5xx)",
            reason_code="blog_http_error",
        )
        return []
    except requests.exceptions.ConnectionError:
        structured_logger.warning(
            "Connection error when fetching blog posts: %s",
            event_code="blog_post_fetch_connection_error",
            reason="Network connection failed while trying to reach the RSS feed.",
            reason_code="blog_conn_error",
        )
        return []
    except requests.exceptions.Timeout:
        structured_logger.warning(
            "Timeout when fetching blog posts: %s",
            event_code="blog_post_fetch_timeout",
            reason="The request to fetch RSS feed exceeded the timeout threshold.",
            reason_code="blog_timeout",
        )
        return []
    except requests.exceptions.RequestException:
        structured_logger.warning(
            "Request exception when fetching blog posts: %s",
            event_code="blog_post_fetch_request_exception",
            reason="General request failure when fetching or parsing RSS feed content.",
            reason_code="blog_req_error",
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
