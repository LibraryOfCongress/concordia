from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import RequestFactory, TestCase
from django.urls import reverse

from concordia.consumers import AssetConsumer
from concordia.utils import get_or_create_reservation_token
from concordia.views import obtain_reservation

from .utils import CreateTestUsers, create_asset, create_item, create_transcription


class TestAssetConsumer(CreateTestUsers, TestCase):
    """
    Normally defining communicator would be in setUp
    and communicator.disconnect would be called in tearDown
    Asynchronous code doesn't seem to work well with those methods
    so those lines are in each test.
    """

    async def test_asset_update(self):
        communicator = WebsocketCommunicator(
            AssetConsumer.as_asgi(), "ws/asset/asset_updates/"
        )
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        asset = await sync_to_async(create_asset)()
        response = await communicator.receive_json_from()
        message = response["message"]
        self.assertEqual(message["type"], "asset_update")
        self.assertEqual(message["asset_pk"], asset.pk)
        self.assertEqual(message["status"], "not_started")
        self.assertEqual(message["latest_transcription"], None)

        await sync_to_async(create_item)(item_id="item-2", project=asset.item.project)
        response = await communicator.receive_nothing()
        self.assertTrue(response)

        user = await sync_to_async(self.create_test_user)()
        transcription = await sync_to_async(create_transcription)(
            asset=asset, user=user
        )
        response = await communicator.receive_json_from()
        message = response["message"]
        self.assertEqual(message["type"], "asset_update")
        self.assertEqual(message["asset_pk"], asset.pk)
        self.assertEqual(message["status"], "in_progress")
        self.assertEqual(message["latest_transcription"]["id"], transcription.pk)

        await communicator.disconnect()

    async def test_asset_reservation_obtained(self):
        asset = await sync_to_async(create_asset)()
        communicator = WebsocketCommunicator(
            AssetConsumer.as_asgi(), "ws/asset/asset_updates/"
        )
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        request_factory = RequestFactory()
        request = request_factory.get("/")
        request.session = {}
        token = get_or_create_reservation_token(request)
        await sync_to_async(obtain_reservation)(asset.pk, token)

        response = await communicator.receive_json_from()
        message = response["message"]
        self.assertEqual(message["type"], "asset_reservation_obtained")
        self.assertEqual(message["asset_pk"], asset.pk)

        await communicator.disconnect()

    async def test_asset_reservation_released(self):
        asset = await sync_to_async(create_asset)()
        await self.async_client.get(
            reverse("reserve-asset", kwargs={"asset_pk": asset.pk})
        )

        communicator = WebsocketCommunicator(
            AssetConsumer.as_asgi(), "ws/asset/asset_updates/"
        )
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        await self.async_client.post(
            reverse("reserve-asset", kwargs={"asset_pk": asset.pk}),
            {"release": "release"},
        )
        response = await communicator.receive_json_from()
        message = response["message"]
        self.assertEqual(message["type"], "asset_reservation_released")
        self.assertEqual(message["asset_pk"], asset.pk)
        await communicator.disconnect()
