from datetime import date
from unittest import mock
from urllib.parse import urlparse

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now

from concordia import api_views
from concordia.models import (
    Asset,
    Campaign,
    Item,
    Topic,
    Transcription,
    User,
)
from concordia.utils import get_anonymous_user

from .utils import (
    JSONAssertMixin,
    create_asset,
    create_item,
    create_project,
    create_topic,
)


class URLAwareEncoderTest(TestCase):
    def test_default(self):
        encoder = api_views.URLAwareEncoder()
        self.assertEqual(encoder.default(None), None)

        obj = mock.Mock(spec=["url"])
        self.assertEqual(encoder.default(obj), obj.url)

        obj = mock.Mock(spec=["get_absolute_url"])
        self.assertEqual(encoder.default(obj), obj.get_absolute_url())

        # Test non-model object
        obj = date.today()
        self.assertEqual(encoder.default(obj), date.today().isoformat())


class APIViewMixinTest(TestCase):
    def setUp(self):
        self.mixin = api_views.APIViewMixin()

    def test_serialize_conctext(self):
        context = {"test-key": "test-value"}
        self.assertEqual(self.mixin.serialize_context(context), context)

    @mock.patch("concordia.api_views.model_to_dict")
    def test_serialize_object(self, mtd_mock):
        return_data = {"test-key": "test-value"}
        mtd_mock.return_value = return_data

        obj = mock.Mock(spec=["get_absolute_url"])
        data = self.mixin.serialize_object(obj)

        self.assertEqual(data, return_data | {"url": obj.get_absolute_url()})

        obj = mock.Mock(spec=[])
        data = self.mixin.serialize_object(obj)

        self.assertEqual(data, return_data)


@mock.patch("concordia.api_views.time")
class APIListViewTest(TestCase):
    def test_serialize_context(self, time_mock):
        time_mock.return_value = "test-time"
        view = api_views.APIListView()
        context = {"object_list": []}

        data = view.serialize_context(context)
        self.assertEqual(data, {"objects": [], "sent": "test-time"})


@override_settings(RATELIMIT_ENABLE=False)
class ConcordiaViewTests(JSONAssertMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.anon_user = get_anonymous_user()

        cls.reviewer = User.objects.create_user(
            username="reviewer", email="tester@example.com"
        )

        cls.test_project = create_project()

        cls.test_topic = create_topic(project=cls.test_project)

        cls.items = [
            create_item(
                item_id=f"item_{i}",
                title=f"Item {i}",
                project=cls.test_project,
                do_save=False,
            )
            for i in range(0, 3)
        ]
        Item.objects.bulk_create(cls.items)

        cls.assets = []
        for item in cls.items:
            cls.assets.append(
                create_asset(
                    title=f"Thumbnail URL test for {item.id}",
                    item=item,
                    download_url="http://tile.loc.gov/image-services/iiif/"
                    "service:music:mussuffrage:mussuffrage-100183:mussuffrage-100183.0001/"
                    "full/pct:100/0/default.jpg",
                    do_save=False,
                )
            )
            for i in range(0, 15):
                cls.assets.append(
                    create_asset(title=f"{item.id} — {i}", item=item, do_save=False)
                )
        Asset.objects.bulk_create(cls.assets)

        cls.transcriptions = []
        for asset in cls.assets:
            last_t = None

            for n in range(0, 3):
                cls.transcriptions.append(
                    Transcription(
                        asset=asset,
                        supersedes=last_t,
                        text=f"{asset} — {n}",
                        user=cls.anon_user,
                    )
                )

        Transcription.objects.bulk_create(cls.transcriptions)

        submitted_t = cls.transcriptions[-1]
        submitted_t.submitted = now()
        submitted_t.full_clean()
        submitted_t.save()

    def get_api_response(self, url, **request_args):
        """
        This issues a call to one of our API views and confirms that the
        response follows our basic conventions of returning a valid JSON
        response
        """

        qs = {"format": "json"}
        if request_args is not None:
            qs.update(request_args)

        resp = self.client.get(url, qs)
        data = self.assertValidJSON(resp)
        return resp, data

    def get_api_list_response(self, url, page_size=10, **request_args):
        """
        This issues a call to one of our API views and confirms that the
        response follows our basic conventions of returning a top level object
        with members“objects” (list) and “pagination” (object).
        """

        qs = {"per_page": page_size}
        if request_args is not None:
            qs.update(request_args)

        resp, data = self.get_api_response(url, **qs)

        self.assertIn("objects", data)
        self.assertIn("pagination", data)

        object_count = len(data["objects"])
        self.assertLessEqual(object_count, page_size)

        self.assertAbsoluteURLs(data["objects"])
        self.assertAbsoluteURLs(data["pagination"])

        return resp, data

    def assertAbsoluteUrl(self, url, allow_none=True):
        """Require a URL to either be None or an absolute URL"""

        if url is None and allow_none:
            return

        parsed = urlparse(url)
        self.assertIn(
            parsed.scheme, ["http", "https"], msg=f"Expected {url} to have HTTP scheme"
        )

        self.assertTrue(parsed.netloc)

    def assertAbsoluteURLs(self, data):
        if isinstance(data, dict):
            for k, v in data.items():
                if k.endswith("url"):
                    self.assertAbsoluteUrl(v)
                elif isinstance(v, (dict, list)):
                    self.assertAbsoluteURLs(v)
        elif isinstance(data, list):
            for i in data:
                self.assertAbsoluteURLs(i)
        else:
            raise TypeError(
                "assertAbsoluteURLs must be called with a dictionary or list"
            )

    def assertAssetStatuses(self, asset_list, expected_statuses):
        asset_pks = [i["id"] for i in asset_list]

        self.assertQuerySetEqual(
            Asset.objects.filter(pk__in=asset_pks).exclude(
                transcription_status__in=expected_statuses
            ),
            [],
        )

    def assertAssetsHaveLatestTranscriptions(self, asset_list):
        asset_pks = {i["id"]: i for i in asset_list}

        for asset in Asset.objects.filter(pk__in=asset_pks.keys()):
            latest_trans = asset.transcription_set.latest("pk")

            if latest_trans is None:
                self.assertIsNone(asset_pks[asset.id]["latest_transcription"])
            else:
                self.assertDictEqual(
                    asset_pks[asset.id]["latest_transcription"],
                    {
                        "id": latest_trans.pk,
                        "text": latest_trans.text,
                        "submitted_by": latest_trans.user_id,
                    },
                )

    def test_topic_list(self):
        resp, data = self.get_api_list_response(reverse("topic-list"))

        self.assertGreater(len(data["objects"]), 0)

        test_topics = {
            i["id"]: i
            for i in Topic.objects.published().values(
                "id", "title", "description", "short_description", "slug"
            )
        }

        for obj in data["objects"]:
            self.assertIn("id", obj)
            self.assertIn("url", obj)
            self.assertDictContainsSubset(test_topics[obj["id"]], obj)

    def test_topic_detail(self):
        resp, data = self.get_api_response(
            reverse("topic-detail", kwargs={"slug": self.test_topic.slug})
        )

        self.assertIn("object", data)
        self.assertNotIn("objects", data)

        serialized_project = data["object"]

        self.assertIn("id", serialized_project)
        self.assertIn("url", serialized_project)
        topic = self.test_topic
        self.assertDictContainsSubset(
            {
                "id": topic.id,
                "title": topic.title,
                "description": topic.description,
                "slug": topic.slug,
                "thumbnail_image": topic.thumbnail_image,
            },
            serialized_project,
        )
        self.assertURLEqual(
            serialized_project["url"], f"http://testserver{topic.get_absolute_url()}"
        )

    def test_campaign_list(self):
        resp, data = self.get_api_list_response(reverse("transcriptions:campaign-list"))

        self.assertGreater(len(data["objects"]), 0)

        test_campaigns = {
            i["id"]: i
            for i in Campaign.objects.published().values(
                "id", "title", "description", "short_description", "slug"
            )
        }

        for obj in data["objects"]:
            self.assertIn("id", obj)
            self.assertIn("url", obj)
            self.assertDictContainsSubset(test_campaigns[obj["id"]], obj)

    def test_campaign_detail(self):
        resp, data = self.get_api_response(
            reverse(
                "transcriptions:campaign-detail",
                kwargs={"slug": self.test_project.campaign.slug},
            )
        )

        self.assertIn("object", data)
        self.assertNotIn("objects", data)

        serialized_project = data["object"]

        self.assertIn("id", serialized_project)
        self.assertIn("url", serialized_project)
        campaign = self.test_project.campaign
        self.assertDictContainsSubset(
            {
                "id": campaign.id,
                "title": campaign.title,
                "description": campaign.description,
                "slug": campaign.slug,
                "metadata": campaign.metadata,
                "thumbnail_image": campaign.thumbnail_image,
            },
            serialized_project,
        )
        self.assertURLEqual(
            serialized_project["url"], f"http://testserver{campaign.get_absolute_url()}"
        )

    def test_project_detail(self):
        project = self.test_project

        resp, data = self.get_api_list_response(project.get_absolute_url())

        # Until we clean up the project view code, projects have two key
        # elements: objects lists the children (i.e. items) and the project
        # itself is in a second top-level “project” object:
        self.assertIn("objects", data)
        self.assertIn("project", data)
        self.assertNotIn("object", data)

        serialized_project = data["project"]

        self.assertIn("id", serialized_project)
        self.assertIn("url", serialized_project)

        self.assertURLEqual(
            serialized_project["url"], f"http://testserver{project.get_absolute_url()}"
        )
        self.assertDictContainsSubset(
            {
                "description": project.description,
                "id": project.id,
                "metadata": project.metadata,
                "slug": project.slug,
                "thumbnail_image": project.thumbnail_image,
                "title": project.title,
            },
            serialized_project,
        )

        for obj in data["objects"]:
            self.assertIn("description", obj)
            self.assertIn("item_id", obj)
            self.assertIn("item_url", obj)
            self.assertIn("metadata", obj)
            self.assertIn("thumbnail_url", obj)
            self.assertIn("title", obj)
            self.assertIn("url", obj)

    def test_item_detail(self):
        item = self.test_project.item_set.first()
        resp, data = self.get_api_list_response(item.get_absolute_url())

        # Until we clean up the project view code, projects have two key
        # elements: objects lists the children (i.e. items) and the project
        # itself is in a second top-level “project” object:
        self.assertIn("objects", data)
        self.assertIn("item", data)
        self.assertNotIn("object", data)

        serialized_item = data["item"]

        self.assertIn("id", serialized_item)
        self.assertIn("url", serialized_item)
        self.assertIn("thumbnail_url", serialized_item)

        self.assertURLEqual(
            serialized_item["url"], f"http://testserver{item.get_absolute_url()}"
        )
        self.assertDictContainsSubset(
            {
                "description": item.description,
                "id": item.id,
                "item_id": item.item_id,
                "metadata": item.metadata,
                "title": item.title,
            },
            serialized_item,
        )

        for obj in data["objects"]:
            self.assertIn("description", obj)
            self.assertIn("difficulty", obj)
            self.assertIn("metadata", obj)
            self.assertIn("image_url", obj)
            self.assertIn("thumbnail_url", obj)
            self.assertIn("resource_url", obj)
            self.assertIn("title", obj)
            self.assertIn("slug", obj)
            self.assertIn("url", obj)
            self.assertIn("year", obj)
            if "Thumbnail test" in obj["title"]:
                self.assertIn("https", obj["thumbnail_url"])
