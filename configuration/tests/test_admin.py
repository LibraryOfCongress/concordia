from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from configuration.models import Configuration


class TestConfigurationAdmin(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass",  # nosec
        )
        self.client.force_login(self.superuser)

        self.config = Configuration.objects.create(
            key="test-key",
            value="Initial value",
            data_type=Configuration.DataType.TEXT,
            description="Initial description",
        )
        self.url = reverse(
            "admin:configuration_configuration_change", args=[self.config.pk]
        )

    def test_change_view_initial_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "test-key")
        self.assertContains(response, "Initial value")

    def test_save_triggers_confirmation(self):
        response = self.client.post(
            self.url,
            {
                "key": self.config.key,
                "value": "Updated value",
                "data_type": Configuration.DataType.TEXT,
                "description": "Updated description",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/configuration_confirm_update.html")
        self.assertContains(response, "Confirm Update of Configuration")

    def test_confirm_save_updates_object(self):
        # Step 1: post to trigger confirmation
        confirmation_response = self.client.post(
            self.url,
            {
                "key": self.config.key,
                "value": "Updated value",
                "data_type": Configuration.DataType.TEXT,
                "description": "Updated description",
            },
        )
        self.assertEqual(confirmation_response.status_code, 200)
        self.assertTemplateUsed(
            confirmation_response, "admin/configuration_confirm_update.html"
        )

        # Step 2: confirm the update
        confirm_response = self.client.post(
            self.url,
            {
                "_confirm_update": "1",
                "key": self.config.key,
                "value": "Updated value",
                "data_type": Configuration.DataType.TEXT,
                "description": "Updated description",
            },
            follow=True,
        )

        changelist_url = reverse("admin:configuration_configuration_changelist")
        self.assertRedirects(confirm_response, changelist_url)
        self.assertContains(confirm_response, "Configuration updated and cached.")
        self.config.refresh_from_db()
        self.assertEqual(self.config.value, "Updated value")
        self.assertEqual(self.config.description, "Updated description")

    def test_cancel_preserves_input(self):
        # Step 1: post to trigger confirmation
        confirmation_response = self.client.post(
            self.url,
            {
                "key": self.config.key,
                "value": "New value",
                "data_type": Configuration.DataType.TEXT,
                "description": "Changed description",
            },
        )
        self.assertEqual(confirmation_response.status_code, 200)

        # Step 2: simulate "Cancel" by posting with cancel_update
        cancel_response = self.client.post(
            self.url,
            {
                "cancel_update": "1",
                "key": self.config.key,
                "value": "New value",
                "data_type": Configuration.DataType.TEXT,
                "description": "Changed description",
            },
        )

        self.assertEqual(cancel_response.status_code, 200)
        self.assertContains(cancel_response, "Changed description")
        self.assertContains(cancel_response, "New value")

        self.config.refresh_from_db()
        self.assertEqual(self.config.value, "Initial value")
        self.assertEqual(self.config.description, "Initial description")

    def test_confirm_save_with_invalid_form(self):
        # Step 1: trigger confirmation with valid initial post
        self.client.post(
            self.url,
            {
                "key": self.config.key,
                "value": "value",
                "data_type": Configuration.DataType.TEXT,
                "description": "desc",
            },
        )

        # Step 2: confirm with missing required field (invalid POST)
        response = self.client.post(
            self.url,
            {
                "_confirm_update": "1",
                # Omit 'key' which is required
                "value": "value",
                "data_type": Configuration.DataType.TEXT,
                "description": "desc",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid data on confirmation.")
        self.config.refresh_from_db()
        self.assertEqual(self.config.value, "Initial value")  # unchanged

    def test_get_value_failure_on_confirmation(self):
        # Create a config with data_type=JSON and invalid JSON
        config = Configuration.objects.create(
            key="bad-json-key",
            value="Not JSON",
            data_type=Configuration.DataType.JSON,
            description="desc",
        )
        url = reverse("admin:configuration_configuration_change", args=[config.pk])

        # Initial POST with invalid JSON triggers get_value failure
        response = self.client.post(
            url,
            {
                "key": config.key,
                "value": "Still not JSON",
                "data_type": Configuration.DataType.JSON,
                "description": "desc",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Validation failed:")

    def test_first_post_invalid_form(self):
        response = self.client.post(
            self.url,
            {
                "key": "",  # key is required, so this makes the form invalid
                "value": "Some value",
                "data_type": Configuration.DataType.TEXT,
                "description": "Bad post",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/change_form.html")
        self.assertContains(response, "This field is required.")
