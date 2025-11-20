from logging import getLogger

from concordia.logging import ConcordiaLogger
from concordia.parser import extract_og_image, fetch_blog_posts

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task(bind=True, ignore_result=True)
def fetch_and_cache_blog_images(self):
    """
    Fetch blog posts and cache their Open Graph images.

    This Celery task iterates over entries returned by ``fetch_blog_posts()``,
    finds each entry's ``<link>`` element, and passes the URL to
    ``extract_og_image()`` so the Open Graph image can be fetched and cached
    for later use.
    """
    for item in fetch_blog_posts():
        link = item.find("link")
        if link is not None:
            extract_og_image(link.text)
