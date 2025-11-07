"""
Signals emitted by Concordia to announce reservation lifecycle events.

Signals:
    reservation_obtained (Signal): Emitted when an asset reservation is created.
        Sender:
            The actor that initiated the reservation (for example, a view).
        Keyword arguments:
            asset_pk (int): Primary key of the reserved asset.
            reservation_token (str): Reservation token.

    reservation_released (Signal): Emitted when an asset reservation is released.
        Sender:
            The actor that released the reservation.
        Keyword arguments:
            asset_pk (int): Primary key of the asset whose reservation was released.
            reservation_token (str): The reservation token that was released.
"""

from django.dispatch import Signal

reservation_obtained: Signal = Signal()

reservation_released: Signal = Signal()
