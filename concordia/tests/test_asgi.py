from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase

from concordia.asgi import application


class TestAssetConsumer(SimpleTestCase):
    async def test_asset_consumer_receives_group_message(self):
        communicator = WebsocketCommunicator(application, "ws/asset/asset_updates/")
        connected, _ = await communicator.connect()

        # trigger asset_update
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "asset_updates",
            {
                "type": "asset_update",
                "message": "hello world",
            },
        )

        response = await communicator.receive_json_from()

        self.assertEqual(response["message"]["message"], "hello world")
        self.assertIn("sent", response)

        await communicator.disconnect()
