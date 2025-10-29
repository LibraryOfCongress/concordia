from unittest import mock

from django.test import TestCase
from requests.models import Response

from concordia.tasks.blog import fetch_and_cache_blog_images


class TaskTestCase(TestCase):
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
