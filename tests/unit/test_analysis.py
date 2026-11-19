import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.application.entities import Food, FoodRequest, RequestStatus
from app.application.errors import InvalidInput
from app.application.services.analysis import analyze_food_requests
from scripts.demo import analyze_dataset

ROOT = Path(__file__).parents[2]


def test_included_demo_is_reproducible_and_explains_competing_requests():
    report = analyze_dataset(ROOT / "data/demo.json")
    assert report == json.loads((ROOT / "data/demo-report.json").read_text())
    assert report["registered_food_kg"] == "33.000"
    assert report["requested_food_kg"] == "27.000"
    assert report["approved_food_kg"] == "12.000"
    assert report["request_counts"] == {"PENDING": 4, "APPROVED": 1, "REJECTED": 1}
    decisions = report["pending_quantity_and_expiry_checks"]
    assert decisions[0]["check"] == "EXPIRED"
    assert decisions[1]["food"] == "Feijão"
    rice = [item for item in decisions if item["food"] == "Arroz"]
    assert all(item["available_kg"] == "8.000" for item in rice)
    assert all(item["check"] == "WITHIN_QUANTITY_AND_EXPIRY_LIMITS" for item in rice)
    assert sum(Decimal(item["requested_kg"]) for item in rice) > Decimal("8")
    assert "independent" in report["interpretation"]


@pytest.fixture
def listing():
    food = Food(uuid4(), uuid4(), "Rice", "Grains", Decimal("10"), date(2026, 11, 19))
    request = FoodRequest(
        uuid4(),
        food.id,
        food.donor_organization_id,
        uuid4(),
        Decimal("6"),
        RequestStatus.PENDING,
        datetime.now(UTC),
    )
    return food, request


def test_empty_analysis_returns_zero():
    result = analyze_food_requests([], [], date(2026, 11, 19))
    assert (
        result["registered_food_kg"]
        == result["requested_food_kg"]
        == result["approved_food_kg"]
        == "0.000"
    )
    assert result["pending_quantity_and_expiry_checks"] == []


def test_expiry_boundary_and_approved_balance_are_enforced(listing):
    food, request = listing
    approved = replace(request, id=uuid4(), status=RequestStatus.APPROVED, quantity_kg=Decimal("5"))
    result = analyze_food_requests([food], [approved, request], date(2026, 11, 19))
    assert result["pending_quantity_and_expiry_checks"][0]["check"] == "INSUFFICIENT_QUANTITY"
    assert result["pending_quantity_and_expiry_checks"][0]["available_kg"] == "5.000"
    exact = replace(request, quantity_kg=Decimal("5"))
    result = analyze_food_requests([food], [approved, exact], date(2026, 11, 19))
    assert (
        result["pending_quantity_and_expiry_checks"][0]["check"]
        == "WITHIN_QUANTITY_AND_EXPIRY_LIMITS"
    )


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate_food",
        "duplicate_request",
        "unknown_food",
        "wrong_donor",
        "own_food",
        "overallocated",
    ],
)
def test_invalid_snapshot_is_rejected(listing, kind):
    food, request = listing
    foods, requests = [food], [request]
    if kind == "duplicate_food":
        foods.append(food)
    elif kind == "duplicate_request":
        requests.append(request)
    elif kind == "unknown_food":
        requests = [replace(request, food_id=uuid4())]
    elif kind == "wrong_donor":
        requests = [replace(request, donor_organization_id=uuid4())]
    elif kind == "own_food":
        requests = [replace(request, recipient_organization_id=food.donor_organization_id)]
    else:
        requests = [replace(request, status=RequestStatus.APPROVED, quantity_kg=Decimal("11"))]
    with pytest.raises(InvalidInput):
        analyze_food_requests(foods, requests, date(2026, 11, 19))


def test_demo_rejects_unlabeled_real_data_and_unknown_organizations(tmp_path):
    data = json.loads((ROOT / "data/demo.json").read_text())
    path = tmp_path / "data.json"
    data["source"]["kind"] = "real"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="synthetic"):
        analyze_dataset(path)
    data["source"]["kind"] = "synthetic"
    data["organizations"] = []
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="unknown organization"):
        analyze_dataset(path)
