import json
from functools import wraps

from django.utils.text import slugify

from concordia.models import Campaign, MediaType


def ensure_slug(original_function):
    @wraps(original_function)
    def inner(*args, **kwargs):
        title = kwargs.get("title")
        slug = kwargs.get("slug")
        if title and slug is None:
            kwargs["slug"] = slugify(title, allow_unicode=True)

        return original_function(*args, **kwargs)

    return inner


@ensure_slug
def create_campaign(
    *,
    title="Test Campaign",
    slug="test-campaign",
    short_description="Short Description",
    description="Test Description",
    published=True,
    **kwargs,
):
    campaign = Campaign(
        title=title, slug=slug, description=description, published=published, **kwargs
    )
    campaign.full_clean()
    campaign.save()
    return campaign


@ensure_slug
def create_project(
    *,
    campaign=None,
    title="Test Project",
    slug="test-project",
    description="Test Description",
    published=True,
    **kwargs,
):
    if campaign is None:
        campaign = create_campaign()

    project = campaign.project_set.create(
        title=title, slug=slug, published=True, **kwargs
    )
    project.full_clean()
    project.save()
    return project


def create_item(
    *,
    project=None,
    title="Test Item",
    item_id="testitem0123456789",
    item_url="http://example.com/item/testitem0123456789/",
    published=True,
    **kwargs,
):
    if project is None:
        project = create_project()

    item = project.item_set.create(
        title=title, item_id=item_id, item_url=item_url, published=True, **kwargs
    )
    item.full_clean()
    item.save()
    return item


@ensure_slug
def create_asset(
    *,
    item=None,
    title="Test Asset",
    slug="test-asset",
    media_type=MediaType.IMAGE,
    media_url="1.jpg",
    published=True,
    **kwargs,
):
    if item is None:
        item = create_item()
    asset = item.asset_set.create(
        title=title,
        slug=slug,
        media_type=media_type,
        published=published,
        media_url=media_url,
        **kwargs,
    )
    asset.full_clean()
    asset.save()
    return asset


class JSONAssertMixin(object):
    def assertValidJSON(self, response, expected_status=200):
        """
        Assert that a response contains valid JSON and return the decoded JSON
        """
        self.assertEqual(response.status_code, expected_status)

        try:
            data = json.loads(response.content.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self.fail(msg=f"response content failed to decode: {exc}")
            raise

        return data
