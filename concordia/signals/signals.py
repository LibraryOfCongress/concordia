import django.dispatch

# signals notify channels of asset reservation - kwargs from handlers
# ["asset_pk", "reservation_token"]

reservation_obtained = django.dispatch.Signal()

reservation_released = django.dispatch.Signal()
