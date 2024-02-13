import json

from django.test import RequestFactory, TestCase

from concordia.admin.views import SerializedObjectView
from concordia.tests.utils import create_card


class TestSerializedObjectView(TestCase):
    def setUp(self):
        self.card = create_card()
        # Every test needs access to the request factory.
        self.factory = RequestFactory()

    def test_get(self):
        request = self.factory.get(
            "/admin/card/",
            {"model_name": "Card", "object_id": 1, "field_name": "title"},
        )
        response = SerializedObjectView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["title"], self.card.title)
