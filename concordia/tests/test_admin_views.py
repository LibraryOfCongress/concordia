import json
from http import HTTPStatus

from django.test import RequestFactory, TestCase
from django.urls import reverse

from concordia.admin.views import (
    SerializedObjectView,
)
from concordia.tests.utils import CreateTestUsers, create_card


class TestFunctionBasedViews(CreateTestUsers, TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = self.create_user(username="tester")

    def test_project_level_export(self):
        self.client.get(reverse("admin:project-level-export"))

    def test_redownload_images_view(self):
        self.client.get(reverse("admin:redownload-images"))

    def test_celery_task_review(self):
        self.client.get(reverse("admin:celery-review"))

    def test_admin_bulk_import_review(self):
        self.client.get(reverse("admin:bulk-review"))

    def test_admin_bulk_import_view(self):
        self.client.get(reverse("admin:bulk-import"))

    def test_admin_site_report_view(self):
        self.client.get(reverse("admin:site-report"))

    def test_admin_retired_site_report_view(self):
        self.client.get(reverse("admin:retired-site-report"))


class TestSerializedObjectView(TestCase):
    def setUp(self):
        self.card = create_card()
        # Every test needs access to the request factory.
        self.factory = RequestFactory()

    def test_exists(self):
        request = self.factory.get(
            "/admin/card/",
            {"model_name": "Card", "object_id": self.card.id, "field_name": "title"},
        )
        response = SerializedObjectView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["title"], self.card.title)

    def test_dne(self):
        request = self.factory.get(
            "/admin/card/",
            {"model_name": "Card", "object_id": 2, "field_name": "title"},
        )
        response = SerializedObjectView.as_view()(request)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertJSONEqual(response.content, {"status": "false"})
