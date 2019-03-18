import json

from channels.generic.websocket import AsyncWebsocketConsumer


class AssetConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("asset_updates", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("asset_updates", self.channel_name)

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]
        message_type = text_data_json["type"]

        # Send message to group
        await self.channel_layer.group_send(
            "asset_updates", {"type": message_type, "message": message}
        )

    # Receive message from group
    async def asset_update(self, message):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"message": message}))

    async def asset_reservation(self, message):
        await self.send(text_data=json.dumps({"message": message}))
