import django.dispatch

reservation_obtained = django.dispatch.Signal(providing_args=["asset_pk", "user_pk"])

reservation_released = django.dispatch.Signal(providing_args=["asset_pk", "user_pk"])
