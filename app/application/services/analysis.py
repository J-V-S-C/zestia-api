from datetime import date
from decimal import Decimal
from uuid import UUID

from app.application.entities import Food, FoodRequest, RequestStatus
from app.application.errors import InvalidInput


def analyze_food_requests(
    foods: list[Food], requests: list[FoodRequest], snapshot_date: date
) -> dict:
    """Quantity/expiry decision support for an explicitly dated data snapshot."""
    listings = {food.id: food for food in foods}
    if len(listings) != len(foods) or len({request.id for request in requests}) != len(requests):
        raise InvalidInput("duplicate_data", "Duplicate food or request identifiers.")
    approved: dict[UUID, Decimal] = {food.id: Decimal("0") for food in foods}
    for request in requests:
        food = listings.get(request.food_id)
        if food is None or request.donor_organization_id != food.donor_organization_id:
            raise InvalidInput("invalid_reference", "Request does not reference its donor's food.")
        if request.recipient_organization_id == food.donor_organization_id:
            raise InvalidInput("own_food_request", "An organization cannot request its own food.")
        if request.status == RequestStatus.APPROVED:
            approved[food.id] += request.quantity_kg
    if any(approved[food.id] > food.quantity_kg for food in foods):
        raise InvalidInput("overallocated_food", "Approved quantity exceeds registered food.")

    def kg(value: Decimal) -> str:
        return format(value, ".3f")

    pending = []
    for request in requests:
        if request.status != RequestStatus.PENDING:
            continue
        food = listings[request.food_id]
        available = food.quantity_kg - approved[food.id]
        if food.expiration_date < snapshot_date:
            result = "EXPIRED"
        elif request.quantity_kg > available:
            result = "INSUFFICIENT_QUANTITY"
        else:
            result = "WITHIN_QUANTITY_AND_EXPIRY_LIMITS"
        pending.append(
            {
                "request_id": str(request.id),
                "food": food.name,
                "requested_kg": kg(request.quantity_kg),
                "available_kg": kg(available),
                "expiration_date": food.expiration_date.isoformat(),
                "check": result,
            }
        )
    pending.sort(key=lambda row: (row["expiration_date"], row["request_id"]))
    return {
        "snapshot_date": snapshot_date.isoformat(),
        "registered_food_kg": kg(sum((food.quantity_kg for food in foods), Decimal("0"))),
        "requested_food_kg": kg(sum((request.quantity_kg for request in requests), Decimal("0"))),
        "approved_food_kg": kg(sum(approved.values(), Decimal("0"))),
        "request_counts": {
            status.value: sum(request.status == status for request in requests)
            for status in RequestStatus
        },
        "pending_quantity_and_expiry_checks": pending,
        "interpretation": (
            "Prioritize unexpired food with earlier expiration. Checks are independent: pending "
            "requests do not reserve quantity. Competing requests require a fresh balance check "
            "and authorized, verified donor approval through the API. "
            "Approved kg are not delivered kg."
        ),
    }
