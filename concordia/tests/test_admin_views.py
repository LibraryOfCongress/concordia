import json
from http import HTTPStatus

from django.test import RequestFactory, TestCase
from django.urls import reverse

from concordia.admin.views import SerializedObjectView, celery_task_review
from concordia.tests.utils import CreateTestUsers, create_card


class TestFunctionBasedViews(CreateTestUsers, TestCase):
    def test_project_level_export(self):
        self.login_user()
        self.assertTrue(self.user.check_password(self.user._password))

        response = self.client.get(reverse("admin:project-level-export"), follow=True)

        self.client.force_login(self.user, backend=None)
        self.assertRedirects(
            response, "/admin/login/?next=/admin/project-level-export/"
        )

        response = self.client.post(reverse("admin:project-level-export"))
        self.assertEqual(response.status_code, 302)

    def test_redownload_images_view(self):
        self.login_user()
        response = self.client.get(reverse("admin:redownload-images"))
        self.assertRedirects(response, "/admin/login/?next=/admin/redownload-images/")

        response = self.client.post(reverse("admin:redownload-images"))
        self.assertEqual(response.status_code, 302)

    def test_celery_task_review(self):
        self.client.get(reverse("admin:celery-review"))
        request = RequestFactory().get(reverse("admin:celery-review"))
        request.user = self.create_user(username="tester")
        celery_task_review(request)

    def test_admin_bulk_import_review(self):
        self.login_user(is_staff=True, is_superuser=True)
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.is_staff)
        self.assertTrue(self.user.is_superuser)
        path = reverse("admin:bulk-review")
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

        data = {}
        response = self.client.post(path, data=data)
        self.assertEqual(response.status_code, 200)

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
