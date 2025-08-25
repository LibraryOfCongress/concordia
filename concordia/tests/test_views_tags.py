from unittest.mock import patch

from django import forms
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.test import (
    TransactionTestCase,
    override_settings,
)
from django.urls import reverse

from concordia.models import (
    Transcription,
)
from concordia.signals.handlers import on_transcription_save

from .utils import (
    CreateTestUsers,
    JSONAssertMixin,
    create_asset,
)


@override_settings(
    RATELIMIT_ENABLE=False, SESSION_ENGINE="django.contrib.sessions.backends.cache"
)
class TagSubmissionViewTests(CreateTestUsers, JSONAssertMixin, TransactionTestCase):
    def test_anonymous_tag_submission(self):
        """Confirm that anonymous users cannot submit tags"""
        asset = create_asset()
        submit_url = reverse("submit-tags", kwargs={"asset_pk": asset.pk})

        resp = self.client.post(submit_url, data={"tags": ["foo", "bar"]})
        self.assertRedirects(resp, "%s?next=%s" % (reverse("login"), submit_url))

    def test_tag_submission(self):
        asset = create_asset()

        self.login_user()

        test_tags = ["foo", "bar"]

        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": test_tags},
        )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertIn("user_tags", data)
        self.assertIn("all_tags", data)

        self.assertEqual(sorted(test_tags), data["user_tags"])
        self.assertEqual(sorted(test_tags), data["all_tags"])

    def test_invalid_tag_submission(self):
        asset = create_asset()

        self.login_user()

        test_tags = ["foo", "bar"]

        with patch("concordia.models.Tag.full_clean") as mock:
            mock.side_effect = forms.ValidationError("Testing error")
            resp = self.client.post(
                reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
                data={"tags": test_tags},
            )
            data = self.assertValidJSON(resp, expected_status=400)
            self.assertIn("error", data)

    def test_tag_submission_with_diacritics(self):
        asset = create_asset()

        self.login_user()

        test_tags = ["Café", "château", "señor", "façade"]

        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": test_tags},
        )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertIn("user_tags", data)
        self.assertIn("all_tags", data)

        self.assertEqual(sorted(test_tags), data["user_tags"])
        self.assertEqual(sorted(test_tags), data["all_tags"])

    def test_tag_submission_with_multiple_users(self):
        asset = create_asset()
        self.login_user()

        test_tags = ["foo", "bar"]

        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": test_tags},
        )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertIn("user_tags", data)
        self.assertIn("all_tags", data)

        self.assertEqual(sorted(test_tags), data["user_tags"])
        self.assertEqual(sorted(test_tags), data["all_tags"])

    def test_duplicate_tag_submission(self):
        """Confirm that tag values cannot be duplicated"""
        asset = create_asset()

        self.login_user()

        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": ["foo", "bar", "baaz"]},
        )
        data = self.assertValidJSON(resp, expected_status=200)

        second_user = self.create_test_user(
            username="second_tester", email="second_tester@example.com"
        )
        self.client.login(username=second_user.username, password=second_user._password)

        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": ["foo", "bar", "quux"]},
        )
        data = self.assertValidJSON(resp, expected_status=200)

        # Even though the user submitted (through some horrible bug) duplicate
        # values, they should not be stored:
        self.assertEqual(["bar", "foo", "quux"], data["user_tags"])
        # Users are allowed to delete other users' tags, so since the second
        # user didn't send the "baaz" tag, it was removed
        self.assertEqual(["bar", "foo", "quux"], data["all_tags"])

    def test_tag_deletion(self):
        asset = create_asset()
        self.login_user()

        initial_tags = ["foo", "bar"]
        self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": initial_tags},
        )
        updated_tags = [
            "foo",
        ]
        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": updated_tags},
        )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertIn("user_tags", data)
        self.assertIn("all_tags", data)

        self.assertCountEqual(updated_tags, data["user_tags"])
        self.assertCountEqual(updated_tags, data["all_tags"])

    def test_tag_deletion_with_multiple_users(self):
        asset = create_asset()
        self.login_user("first_user")
        initial_tags = ["foo", "bar"]
        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": initial_tags},
        )
        self.assertIn(
            "first_user",
            asset.userassettagcollection_set.values().values_list(
                "user__username", flat=True
            ),
        )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertIn("user_tags", data)
        self.assertIn("all_tags", data)
        self.assertCountEqual(initial_tags, data["user_tags"])
        self.assertCountEqual(initial_tags, data["all_tags"])

        self.client.logout()

        second_user = self.create_test_user("second_user")
        self.client.login(username=second_user.username, password=second_user._password)
        updated_tags = [
            "foo",
        ]
        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": updated_tags},
        )
        data = self.assertValidJSON(resp, expected_status=200)

        self.assertIn(
            "second_user",
            asset.userassettagcollection_set.values().values_list(
                "user__username", flat=True
            ),
        )
        self.assertEqual(asset.userassettagcollection_set.count(), 2)
        self.assertEqual(
            User.objects.filter(userassettagcollection__asset=asset).count(), 2
        )
        self.assertIn("user_tags", data)
        self.assertIn("all_tags", data)
        self.assertCountEqual(updated_tags, data["user_tags"])

    def tearDown(self):
        # We'll test the signal handler separately
        post_save.connect(on_transcription_save, sender=Transcription)
