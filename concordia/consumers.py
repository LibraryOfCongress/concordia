import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer


class AssetConsumer(WebsocketConsumer):
    def connect(self):
        self.asset_id = self.scope["url_route"]["kwargs"]["asset_id"]
        self.asset_group_name = self.asset_id
        print("************CONNECT*****************************************")
        print(self.asset_group_name)
        # Join group
        async_to_sync(
            self.channel_layer.group_add(self.asset_group_name, self.channel_name)
        )

        self.accept()

    def disconnect(self, close_code):
        # Leave group
        print("******************DISCONNECT**********************************")
        print(self.asset_group_name)
        async_to_sync(
            self.channel_layer.group_discard(self.asset_group_name, self.channel_name)
        )

    # Receive message from WebSocket
    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]
        print("*************RECEIVE*************************")
        print("Received message")
        print(message)

        # Send message to group
        async_to_sync(
            self.channel_layer.group_send(
                self.asset_group_name, {"type": "asset_update", "message": message}
            )
        )

    # Receive message from group
    def asset_update(self, message):
        print("**********************UPDATE********************")
        print(message)

        # Send message to WebSocket
        async_to_sync(
            self.channel_layer.group_send(
                self.asset_group_name,
                {"type": "asset_update", "message": "This is an asset update message"},
            )
        )
