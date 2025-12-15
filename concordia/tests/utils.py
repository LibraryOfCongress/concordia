import json
from functools import wraps
from secrets import token_hex

from django.utils.text import slugify

from concordia.models import (
    Asset,
    Banner,
    Campaign,
    CampaignRetirementProgress,
    Card,
    CardFamily,
    CarouselSlide,
    ConcordiaFile,
    Guide,
    HelpfulLink,
    Item,
    MediaType,
    Project,
    ResearchCenter,
    SimplePage,
    SiteReport,
    Tag,
    Topic,
    Transcription,
    User,
    UserAssetTagCollection,
    UserProfileActivity,
)


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
    unlisted=False,
    status=Campaign.Status.ACTIVE,
    do_save=True,
    **kwargs,
):
    campaign = Campaign(
        title=title,
        slug=slug,
        description=description,
        unlisted=unlisted,
        published=published,
        status=status,
        **kwargs,
    )
    campaign.full_clean()
    if do_save:
        campaign.save()
    return campaign


def create_simple_page(*, do_save=True, **kwargs):
    simple_page = SimplePage(**kwargs)
    if do_save:
        simple_page.save()
    return simple_page


def create_site_report(*, do_save=True, **kwargs):
    site_report = SiteReport(**kwargs)
    if do_save:
        site_report.save()
    return site_report


@ensure_slug
def create_topic(
    *,
    project=None,
    title="Test Topic",
    slug="test-topic",
    description="Test Description",
    published=True,
    unlisted=False,
    do_save=True,
    **kwargs,
):
    if project is None:
        project = create_project(published=published)

    topic = Topic(
        title=title,
        slug=slug,
        description=description,
        unlisted=unlisted,
        published=published,
        **kwargs,
    )
    topic.full_clean()
    if do_save:
        topic.save()

    topic.project_set.add(project)

    if do_save:
        topic.save()
    return topic


@ensure_slug
def create_project(
    *,
    campaign=None,
    title="Test Project",
    slug="test-project",
    description="Test Description",
    published=True,
    do_save=True,
    **kwargs,
):
    if campaign is None:
        campaign = create_campaign(published=published)

    project = Project(
        campaign=campaign, title=title, slug=slug, published=published, **kwargs
    )
    project.full_clean()
    if do_save:
        project.save()
    return project


def create_item(
    *,
    project=None,
    title="Test Item",
    item_id="testitem.0123456789",
    item_url="http://example.com/item/testitem.0123456789/",
    published=True,
    do_save=True,
    **kwargs,
):
    if project is None:
        project = create_project(published=published)

    item = Item(
        project=project,
        title=title,
        item_id=item_id,
        item_url=item_url,
        published=published,
        **kwargs,
    )
    item.full_clean()
    if do_save:
        item.save()
    return item


@ensure_slug
def create_asset(
    *,
    item=None,
    title="Test Asset",
    slug="test-asset",
    media_type=MediaType.IMAGE,
    published=True,
    storage_image="unittest1.jpg",
    do_save=True,
    **kwargs,
):
    if item is None:
        item = create_item(published=published)
    asset = Asset(
        item=item,
        campaign=item.project.campaign,
        title=title,
        slug=slug,
        media_type=media_type,
        published=published,
        storage_image=storage_image,
        **kwargs,
    )
    asset.full_clean()
    if do_save:
        asset.save()
    return asset


def create_transcription(*, asset=None, user=None, do_save=True, **kwargs):
    if asset is None:
        asset = create_asset()
    if user is None:
        user = CreateTestUsers.create_user(f"asset-{asset.id}-user")
    transcription = Transcription(asset=asset, user=user, **kwargs)
    transcription.full_clean()
    if do_save:
        transcription.save()
    return transcription


def create_tag(*, value="tag-value", do_save=True, **kwargs):
    tag = Tag(value=value, **kwargs)
    tag.full_clean()
    if do_save:
        tag.save()
    return tag


def create_tag_collection(*, tag=None, asset=None, user=None, **kwargs):
    # This function doesn't use do_save because ManyToMany fields don't
    # work until the model is saved.
    if tag is None:
        tag = create_tag()
    if asset is None:
        asset = create_asset()
    if user is None:
        user = CreateTestUsers.create_user("tag-user")
    tag_collection = UserAssetTagCollection(asset=asset, user=user, **kwargs)
    tag_collection.full_clean()
    tag_collection.save()
    tag_collection.tags.add(tag)
    return tag_collection


def create_banner(*, slug="Test Banner", do_save=True, **kwargs):
    banner = Banner(slug=slug, **kwargs)
    if do_save:
        banner.save()
    return banner


def create_card(*, title="Test Card", do_save=True, **kwargs):
    card = Card(title=title, **kwargs)
    if do_save:
        card.save()
    return card


def create_card_family(*, slug="test-card-family", do_save=True, **kwargs):
    card_family = CardFamily(slug=slug, **kwargs)
    if do_save:
        card_family.save()
    return card_family


def create_carousel_slide(*, headline="Test Headline", do_save=True, **kwargs):
    slide = CarouselSlide(**kwargs)
    if do_save:
        slide.save()
    return slide


def create_guide(*, do_save=True, **kwargs):
    guide = Guide(**kwargs)
    if do_save:
        guide.save()
    return guide


def create_helpful_link(*, title="Test Helpful Link", do_save=True, **kwargs):
    link = HelpfulLink(title=title, **kwargs)
    if do_save:
        link.save()
    return link


def create_concordia_file(
    *, name="Test Concordia File", uploaded_file="file.pdf", do_save=True, **kwargs
):
    concordia_file = ConcordiaFile(name=name, uploaded_file=uploaded_file, **kwargs)
    if do_save:
        concordia_file.save()
    return concordia_file


def create_user_profile_activity(
    *,
    campaign=None,
    user=None,
    do_save=True,
    **kwargs,
):
    if campaign is None:
        campaign = create_campaign()
    if user is None:
        user = CreateTestUsers.create_user("profile-user")
    activity = UserProfileActivity(campaign=campaign, user=user)
    if do_save:
        activity.save()
    return activity


def create_campaign_retirement_progress(
    *,
    campaign=None,
    do_save=True,
    **kwargs,
):
    if campaign is None:
        campaign = create_campaign()
    progress = CampaignRetirementProgress(campaign=campaign)
    if do_save:
        progress.save()
    return progress


def create_research_center(*, title="Test Research Center", do_save=True, **kwargs):
    center = ResearchCenter(title=title, **kwargs)
    if do_save:
        center.save()
    return center


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


class CreateTestUsers(object):
    def login_user(self, username="tester", **kwargs):
        """
        Create a user and log the user in
        """
        if not hasattr(self, "user") or self.user is None:
            self.user = self.create_test_user(username, **kwargs)

        self.client.login(username=self.user.username, password=self.user._password)

    def logout_user(self):
        self.client.logout()
        self.user = None

    @classmethod
    def create_user(cls, username, is_active=True, **kwargs):
        if "email" not in kwargs:
            kwargs["email"] = f"{username}@example.com"

        user = User.objects.create_user(username=username, **kwargs)
        fake_pw = token_hex(24)
        user.is_active = is_active
        user.set_password(fake_pw)
        user.save()

        user._password = fake_pw

        return user

    @classmethod
    def create_test_user(cls, username="testuser", **kwargs):
        """
        Creates an activated test User account
        """
        return cls.create_user(username, is_active=True, **kwargs)

    @classmethod
    def create_inactive_user(cls, username="testinactiveuser", **kwargs):
        """
        Creates an inactive test User account
        """
        return cls.create_user(username, is_active=False, **kwargs)

    @classmethod
    def create_staff_user(cls, username="teststaffuser", **kwargs):
        """
        Creates a staff test User account
        """
        return cls.create_user(username, is_staff=True, is_active=True, **kwargs)

    @classmethod
    def create_super_user(cls, username="testsuperuser", **kwargs):
        """
        Creates a super user User account
        """
        return cls.create_user(
            username, is_staff=True, is_superuser=True, is_active=True, **kwargs
        )


class CacheControlAssertions(object):
    def assertUncacheable(self, response):
        self.assertIn("Cache-Control", response)
        self.assertIn("no-cache", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])

    def assertCachePrivate(self, response):
        self.assertIn("Cache-Control", response)
        self.assertIn("private", response["Cache-Control"])


class StreamingTestMixin(object):
    def get_streaming_content(self, response):
        self.assertTrue(response.streaming)
        return b"".join(response.streaming_content)
