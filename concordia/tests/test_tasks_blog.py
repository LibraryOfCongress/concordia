from unittest import mock

from django.test import TestCase
from requests.models import Response

from concordia.tasks.blog import fetch_and_cache_blog_images


class BlogTaskTestCase(TestCase):
    @mock.patch("concordia.tasks.blog.extract_og_image")
    @mock.patch("concordia.parser.requests.get")
    def test_fetch_and_cache_blog_images(self, mock_get, mock_extract):
        link1 = "https://blogs.loc.gov/thesignal/2025/05/volunteers-ocr/"
        link2 = "https://blogs.loc.gov/thesignal/2025/02/douglass-day-2025/"
        rss = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item><link>%s</link></item><item><link>%s</link></item>
          </channel>
        </rss>""" % (
            link1,
            link2,
        )
        mock_response = mock.MagicMock(spec=Response)
        mock_response.content = rss
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        # run the celery task
        fetch_and_cache_blog_images()

        mock_extract.assert_any_call(link1)
        mock_extract.assert_any_call(link2)
        self.assertEqual(mock_extract.call_count, 2)

    @mock.patch("concordia.tasks.blog.extract_og_image")
    @mock.patch("concordia.tasks.blog.fetch_blog_posts")
    def test_skips_items_with_no_link(self, mock_fetch, mock_extract):
        # Provide one item without a link and one with a link to make
        # sure we handle no link correctly
        class DummyLink:
            def __init__(self, text):
                self.text = text

        class DummyItem:
            def __init__(self, link):
                self._link = link

            def find(self, name):
                return self._link if name == "link" else None

        item_no_link = DummyItem(None)
        item_with_link = DummyItem(DummyLink("https://example.invalid/post"))
        mock_fetch.return_value = [item_no_link, item_with_link]

        fetch_and_cache_blog_images()

        mock_extract.assert_called_once_with("https://example.invalid/post")
