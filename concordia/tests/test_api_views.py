from django.test import TestCase, override_settings
from django.urls import reverse

from concordia.models import Asset, Item, Transcription, TranscriptionStatus
from concordia.utils import get_anonymous_user

from .utils import JSONAssertMixin, create_asset, create_item, create_project


@override_settings(RATELIMIT_ENABLE=False)
class ConcordiaViewTests(JSONAssertMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        anon_user = get_anonymous_user()

        project = create_project()

        cls.items = [
            create_item(
                item_id=f"item_{i}", title=f"Item {i}", project=project, do_save=False
            )
            for i in range(0, 3)
        ]
        Item.objects.bulk_create(cls.items)

        cls.assets = []
        for item in cls.items:
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
                        user=anon_user,
                    )
                )
        Transcription.objects.bulk_create(cls.transcriptions)

    def get_asset_list(self, url, page_size=23):
        resp = self.client.get(url, {"per_page": page_size})
        data = self.assertValidJSON(resp)

        self.assertIn("objects", data)
        object_count = len(data["objects"])
        self.assertLessEqual(object_count, 23)

        if object_count >= page_size:
            self.assertIn("pagination", data)
        else:
            self.assertNotIn("pagination", data)

        return resp, data

    def assertAssetStatuses(self, asset_list, expected_statuses):
        asset_pks = [i["id"] for i in asset_list]

        self.assertQuerysetEqual(
            Asset.objects.filter(pk__in=asset_pks).exclude(
                transcription_status__in=expected_statuses
            ),
            [],
        )

    def test_asset_list(self):
        resp, data = self.get_asset_list(reverse("assets-list-json"))

    def test_transcribable_asset_list(self):
        resp, data = self.get_asset_list(reverse("transcribe-assets-json"))

        self.assertAssetStatuses(
            data["objects"],
            [TranscriptionStatus.NOT_STARTED, TranscriptionStatus.IN_PROGRESS],
        )

    def test_reviewable_asset_list(self):
        resp, data = self.get_asset_list(reverse("review-assets-json"))

        self.assertAssetStatuses(data["objects"], [TranscriptionStatus.SUBMITTED])
