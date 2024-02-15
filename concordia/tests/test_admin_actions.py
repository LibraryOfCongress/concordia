from django.contrib.auth.models import User
from django.http import HttpRequest
from django.test import TestCase

from concordia.admin.actions import (
    anonymize_action,
    publish_item_action,
    unpublish_item_action,
)
from concordia.models import Asset, Item
from concordia.tests.utils import CreateTestUsers, create_asset, create_item


class MockModelAdmin:
    pass


request = HttpRequest()
modeladmin = MockModelAdmin()


class UserAdminActionTest(TestCase, CreateTestUsers):
    def setUp(self):
        self.user1 = self.create_user("user1")
        self.user2 = self.create_user("user2")
        self.user3 = self.create_user("user3")

    def test_anonymize_action(self):
        queryset = User.objects.filter(pk__in=(self.user1.pk, self.user3.pk))
        anonymize_action(modeladmin, request, queryset)
        user1 = User.objects.get(pk=self.user1.pk)
        user2 = User.objects.get(pk=self.user2.pk)
        user3 = User.objects.get(pk=self.user3.pk)

        self.assertIn("Anonymized", user1.username)
        self.assertEqual(self.user2.username, user2.username)
        self.assertIn("Anonymized", user3.username)

        self.assertEqual("", user1.email)
        self.assertEqual(self.user2.email, user2.email)
        self.assertEqual("", user3.email)

        self.assertFalse(user1.has_usable_password())
        self.assertTrue(user2.has_usable_password())
        self.assertFalse(user3.has_usable_password())

        self.assertFalse(user1.check_password(self.user1._password))
        self.assertTrue(user2.check_password(self.user2._password))
        self.assertFalse(user3.check_password(self.user3._password))

        self.assertFalse(user1.is_active)
        self.assertTrue(user2.is_active)
        self.assertFalse(user3.is_active)


class ItemAdminActionTest(TestCase):
    def _setUp(self, published=True):
        self.asset1 = create_asset(published=published)
        self.item1 = self.asset1.item
        self.project = self.item1.project

        self.item2 = create_item(project=self.project, item_id="2", published=published)
        self.asset2 = create_asset(
            item=self.item2, slug="test-asset-slug-2", published=published
        )

        self.item3 = create_item(project=self.project, item_id="3", published=published)
        self.asset3 = create_asset(
            item=self.item3, slug="test-asset-slug-3", published=published
        )
        self.asset4 = create_asset(
            item=self.item3, slug="test-asset-slug-4", published=published
        )

    def test_publish_item_action(self):
        self._setUp(False)
        queryset = Item.objects.filter(pk__in=[self.item1.pk, self.item3.pk])
        publish_item_action(modeladmin, request, queryset)
        item1 = Item.objects.get(pk=self.item1.pk)
        asset1 = Asset.objects.get(pk=self.asset1.pk)
        item2 = Item.objects.get(pk=self.item2.pk)
        asset2 = Asset.objects.get(pk=self.asset2.pk)
        item3 = Item.objects.get(pk=self.item3.pk)
        asset3 = Asset.objects.get(pk=self.asset3.pk)
        asset4 = Asset.objects.get(pk=self.asset4.pk)

        self.assertTrue(item1.published)
        self.assertTrue(asset1.published)
        self.assertFalse(item2.published)
        self.assertFalse(asset2.published)
        self.assertTrue(item3.published)
        self.assertTrue(asset3.published)
        self.assertTrue(asset4.published)

    def test_unpublish_item_action(self):
        self._setUp(True)
        queryset = Item.objects.filter(pk__in=[self.item1.pk, self.item3.pk])
        unpublish_item_action(modeladmin, request, queryset)
        item1 = Item.objects.get(pk=self.item1.pk)
        asset1 = Asset.objects.get(pk=self.asset1.pk)
        item2 = Item.objects.get(pk=self.item2.pk)
        asset2 = Asset.objects.get(pk=self.asset2.pk)
        item3 = Item.objects.get(pk=self.item3.pk)
        asset3 = Asset.objects.get(pk=self.asset3.pk)
        asset4 = Asset.objects.get(pk=self.asset4.pk)

        self.assertFalse(item1.published)
        self.assertFalse(asset1.published)
        self.assertTrue(item2.published)
        self.assertTrue(asset2.published)
        self.assertFalse(item3.published)
        self.assertFalse(asset3.published)
        self.assertFalse(asset4.published)
