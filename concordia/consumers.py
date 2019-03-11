import json

from channels.generic.websocket import WebsocketConsumer


class AssetConsumer(WebsocketConsumer):
    def connect(self):
        self.asset_id = self.scope["url_route"]["kwargs"]["asset_id"]
        self.asset_group_name = "asset_%s" % self.asset_id

        # Join group
        self.channel_layer.group_add(self.asset_group_name, self.channel_name)

        self.accept()

    def disconnect(self, close_code):
        # Leave group
        self.channel_layer.group_discard(self.asset_group_name, self.channel_name)

    # Receive message from WebSocket
    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]

        # Send message to group
        self.channel_layer.group_send(
            self.asset_group_name, {"type": "asset_update", "message": message}
        )

    # Receive message from group
    def asset_update(self, event):
        message = event["message"]

        # Send message to WebSocket
        self.send(text_data=json.dumps({"message": message}))
