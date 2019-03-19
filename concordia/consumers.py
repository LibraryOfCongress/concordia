import time

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class AssetConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("asset_updates", self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard("asset_updates", self.channel_name)

    async def asset_update(self, message):
        await self.send_json(
            {"message": message, "message_timestamp": int(time.time())}
        )

    async def asset_reservation(self, message):
        await self.send_json(
            {"message": message, "message_timestamp": int(time.time())}
        )
