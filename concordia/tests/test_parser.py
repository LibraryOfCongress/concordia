from unittest import mock

import requests
from django.test import TestCase
from requests.models import Response

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
</html"""
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
