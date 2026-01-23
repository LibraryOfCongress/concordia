from types import SimpleNamespace
from unittest import mock

import requests
from django.test import TestCase
from requests.models import Response

import concordia.parser as parser_mod
from concordia.parser import extract_og_image, fetch_blog_posts, paginate_blog_posts

TITLE = "What’s New Online at the Library of Congress: May 2025"
LINK = "https://blogs.loc.gov/thesignal/2025/05/new-loc-may-2025/"
RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>The Signal</title>
    <item>
      <title>%s</title>
      <link>%s</link>
      <description><![CDATA[Interested in learning more about what’...]]></description>
    </item>
    <item>
      <title>Volunteers Leverage OCR to Transcribe Library of Congress Digit...</title>
      <description>
        <![CDATA[Today’s guest post is from Lauren Algee, a Senior Digital Collec...]]>
      </description>
    </item>
  </channel>
</rss>""" % (
    TITLE,
    LINK,
)
IMAGE = "https://blogs.loc.gov/thesignal/files/2025/05/loc-2017698702.png"
HTML = (
    """<html>
  <head>
    <meta property="og:image" content="%s"/>
  </head>
  <body></body>
</html>"""
    % IMAGE
)


class ParserTestCase(TestCase):
    @mock.patch("requests.get")
    def test_extract_og_image(self, mock_urlopen):
        mock_response = mock.MagicMock(spec=Response)
        mock_response.text = HTML
        mock_response.headers = {"Content-Type": "text/html"}
        mock_urlopen.return_value = mock_response

        image = extract_og_image("https://example.com/post1")
        self.assertEqual(image, IMAGE)

    @mock.patch("concordia.parser.extract_og_image")
    @mock.patch("requests.get")
    def test_paginate_blog_posts(self, mock_urlopen, mock_extract_og_image):
        mock_response = mock.MagicMock(spec=Response)
        mock_response.content = RSS
        mock_response.status_code = 200
        mock_urlopen.return_value = mock_response

        mock_extract_og_image.return_value = IMAGE

        feed_items = paginate_blog_posts()

        self.assertEqual(len(feed_items), 1)
        self.assertEqual(len(feed_items[0]), 2)
        feed_item = feed_items[0][0]
        self.assertEqual(feed_item["title"], TITLE)
        self.assertEqual(feed_item["link"], LINK)
        self.assertEqual(feed_item["og_image"], IMAGE)

    @mock.patch("concordia.parser.structured_logger.warning")
    @mock.patch("concordia.parser.requests.get")
    def test_get_http_error(self, mock_get, mock_logger):
        mock_response = mock.Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "500 Server Error"
        )
        mock_get.return_value = mock_response
        result = fetch_blog_posts()
        self.assertEqual(result, [])
        mock_logger.assert_called()

    @mock.patch("concordia.parser.structured_logger.warning")
    @mock.patch("concordia.parser.requests.get")
    def test_get_exception_timeout(self, mock_get, mock_logger):
        mock_get.side_effect = requests.exceptions.Timeout()
        result = fetch_blog_posts()
        self.assertEqual(result, [])
        mock_logger.assert_called()

    @mock.patch("concordia.parser.structured_logger.warning")
    @mock.patch("concordia.parser.requests.get")
    def test_get_connection_error(self, mock_get, mock_logger):
        mock_get.side_effect = requests.exceptions.ConnectionError()
        result = fetch_blog_posts()
        self.assertEqual(result, [])
        mock_logger.assert_called()

    @mock.patch("concordia.parser.structured_logger.warning")
    @mock.patch("concordia.parser.requests.get")
    def test_get_request_exception(self, mock_get, mock_logger):
        mock_get.side_effect = requests.exceptions.RequestException()
        result = fetch_blog_posts()
        self.assertEqual(result, [])
        mock_logger.assert_called()
        call_args, call_kwargs = mock_logger.call_args
        self.assertEqual("blog_req_error", call_kwargs["reason_code"])

    def test_ogimageparser_parses_meta_and_sets_og_image(self):
        parser = parser_mod.OGImageParser()
        html_document = (
            "<html><head>"
            '<meta property="og:title" content="ignored"/>'
            '<meta property="og:image" content="http://ex.com/img.png?x=Tom&amp;Jerry"/>'
            "</head><body></body></html>"
        )
        parser.feed(html_document.replace("&amp;", "&"))
        self.assertEqual(parser.og_image, "http://ex.com/img.png?x=Tom&Jerry")

    @mock.patch.object(parser_mod.structured_logger, "warning")
    @mock.patch.object(parser_mod.requests, "get")
    def test_extract_og_image_request_exception_logs_and_returns_none(
        self, requests_get_mock, logger_warning_mock
    ):
        requests_get_mock.side_effect = parser_mod.requests.RequestException
        result = parser_mod.extract_og_image("http://ex.com/bad")
        self.assertIsNone(result)
        self.assertEqual(
            logger_warning_mock.call_args.kwargs.get("reason_code"),
            "ogi_req_fail_fetch",
        )

    @mock.patch.object(parser_mod, "extract_og_image", return_value="fetched.png")
    @mock.patch.object(parser_mod, "cache")
    def test_get_og_image_calls_extract_on_cache_miss(
        self, cache_mock, extract_og_image_mock
    ):
        cache_mock.get.return_value = None
        value = parser_mod.get_og_image("http://ex.com/post2")
        self.assertEqual(value, "fetched.png")
        extract_og_image_mock.assert_called_once_with("http://ex.com/post2")

    @mock.patch.object(parser_mod, "extract_og_image")
    @mock.patch.object(parser_mod, "cache")
    def test_get_og_image_uses_cache_when_present(
        self, cache_mock, extract_og_image_mock
    ):
        cache_mock.get.return_value = "cached.png"
        value = parser_mod.get_og_image("http://ex.com/post")
        self.assertEqual(value, "cached.png")
        extract_og_image_mock.assert_not_called()

    def _make_item_element(self, title, link):
        def find(tag):
            if tag == "title":
                return SimpleNamespace(text=title)
            if tag == "link":
                return SimpleNamespace(text=link)
            return None

        return SimpleNamespace(find=find)

    @mock.patch.object(parser_mod, "get_og_image")
    @mock.patch.object(parser_mod, "fetch_blog_posts")
    def test_paginate_blog_posts_segments_and_includes_og_images(
        self, fetch_blog_posts_mock, get_og_image_mock
    ):
        items = [
            self._make_item_element(f"T{i}", f"http://ex.com/{i}") for i in range(1, 7)
        ]

        def get_og_image_side_effect(url):
            n = int(url.rsplit("/", 1)[-1])
            return f"http://img/{n}.png" if n <= 4 else None

        fetch_blog_posts_mock.return_value = items
        get_og_image_mock.side_effect = get_og_image_side_effect

        segmented = paginate_blog_posts()
        self.assertEqual(len(segmented), 2)
        self.assertEqual(len(segmented[0]), 3)
        self.assertEqual(len(segmented[1]), 3)

        first = segmented[0][0]
        self.assertEqual(first["title"], "T1")
        self.assertEqual(first["link"], "http://ex.com/1")
        self.assertEqual(first["og_image"], "http://img/1.png")

        last = segmented[1][2]
        self.assertEqual(last["title"], "T6")
        self.assertEqual(last["link"], "http://ex.com/6")
        self.assertNotIn("og_image", last)

    @mock.patch.object(parser_mod, "fetch_blog_posts", return_value=[])
    def test_paginate_blog_posts_with_no_items_returns_single_empty_segment(
        self, fetch_blog_posts_mock
    ):
        segmented = paginate_blog_posts()
        self.assertEqual(segmented, [[]])
