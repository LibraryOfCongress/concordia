import json

from channels.generic.websocket import AsyncWebsocketConsumer


class AssetConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.asset_id = self.scope["url_route"]["kwargs"]["asset_id"]
        self.asset_group_name = self.asset_id
        # Join group
        await self.channel_layer.group_add(self.asset_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Leave group
        await self.channel_layer.group_discard(self.asset_group_name, self.channel_name)

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]
        # Send message to group
        await self.channel_layer.group_send(
            self.asset_group_name, {"type": "asset_update", "message": message}
        )

    # Receive message from group
    async def asset_update(self, message):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"message": message}))
