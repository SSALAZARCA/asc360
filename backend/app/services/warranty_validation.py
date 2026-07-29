"""
`sdd/distributor-vehicle-delivery` — the warranty lower-bound invariant.

A single, pure implementation reused at all 3 order-date write paths
(`POST /orders/`, `create_historical_order`, `PUT /superadmin/data/orders/{id}`)
wired in PR2. No DB session, no layering cycle: every call site already
holds (or can trivially load) the `Vehicle` object.
"""
from datetime import date, datetime
from typing import Optional, Union

from fastapi import HTTPException


def ensure_order_date_after_delivery(
    vehicle, order_date: Optional[Union[date, datetime]]
) -> None:
    """The warranty invariant: an order's effective date must never precede
    the vehicle's registered `delivery_date`. Comparison is DAY-precision
    (a bike can be sold and receive its first service the same day).

    NO-OP when `vehicle` is `None`, `order_date` is `None`, or
    `vehicle.delivery_date` is `None` -- vehicles that entered through
    normal reception (not yet backfilled/delivered through the Distribuidor
    screen) are unvalidatable by construction and MUST pass through
    untouched, keeping day-1 behaviour byte-identical.
    """
    if vehicle is None or order_date is None:
        return

    delivery_date = getattr(vehicle, "delivery_date", None)
    if delivery_date is None:
        return

    effective_date = order_date.date() if isinstance(order_date, datetime) else order_date

    if effective_date < delivery_date:
        raise HTTPException(
            status_code=422,
            detail=(
                "La fecha de la orden no puede ser anterior a la fecha de "
                f"entrega del vehículo ({delivery_date.isoformat()})."
            ),
        )
