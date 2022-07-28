import django.dispatch

reservation_obtained = django.dispatch.Signal(
    providing_args=["asset_pk", "reservation_token"]
)

reservation_released = django.dispatch.Signal(
    providing_args=["asset_pk", "reservation_token"]
)
