from django.test import Client, TestCase
from django.urls import reverse

from concordia.models import Asset, Transcription, TranscriptionStatus


class ActionTests(TestCase):
    def setUp(self):
        Transcription(
            asset=Asset(),
            status=TranscriptionStatus.SUBMITTED,
        )
        self.assets = Asset.objects.all()
        self.client = Client()

    def test_change_status_to_completed(self):
        change_url = reverse("admin:concordia_transcription_changelist")
        data = {
            "action": "change_status_to_completed",
            # '_selected_action': Asset.objects.filter(...).values_list('pk', flat=True)
        }
        response = self.client.post(change_url, data, follow=True)
        self.assertEqual(response.status_code, 200)
