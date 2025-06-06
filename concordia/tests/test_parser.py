from unittest import mock

from django.test import TestCase

from concordia.parser import fetch_blog_posts

TITLE = "What’s New Online at the Library of Congress: May 2025"
LINK = "https://blogs.loc.gov/thesignal/2025/05/new-loc-may-2025/"
DESCRIPTION = "Interested in learning more about what’s new in the Library of Congr..."
RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>The Signal</title>
    <item>
      <title>%s</title>
      <link>%s</link>
      <description><![CDATA[%s]]></description>
    </item>
    <item>
      <title>Volunteers Leverage OCR to Transcribe Library of Congress Digit...</title>
      <link>https://blogs.loc.gov/thesignal/2025/05/volunteers-ocr/</link>
      <description>
        <![CDATA[Today’s guest post is from Lauren Algee, a Senior Digital Collec...]]>
      </description>
    </item>
  </channel>
</rss>""" % (
    TITLE,
    LINK,
    DESCRIPTION,
)


def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        content = RSS

    return MockResponse()


class ParserTestCase(TestCase):
    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_fetch_blog_posts(self, mock_get):
        items = fetch_blog_posts()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], TITLE)
        self.assertEqual(items[0]["link"], LINK)
        self.assertEqual(items[0]["description"], DESCRIPTION)
