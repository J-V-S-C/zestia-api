import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.infrastructure.persistence.metrics_queries import SqlAlchemyMetricsRepository
from app.infrastructure.persistence.orm import (
    AccountRecord,
    FoodRecord,
    FoodRequestRecord,
    OrganizationRecord,
)
from scripts.demo import analyze_dataset

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[2]


def test_demo_report_matches_real_postgres_aggregates(database):
    data = json.loads((ROOT / "data/demo.json").read_text())
    with Session(database) as session, session.begin():
        for organization in data["organizations"]:
            owner = uuid4()
            session.add(
                AccountRecord(
                    id=owner,
                    email=f"{owner}@example.com",
                    password_hash="unused-synthetic-fixture",
                    role="USER",
                )
            )
            session.flush()
            session.add(
                OrganizationRecord(
                    id=UUID(organization["id"]),
                    owner_account_id=owner,
                    name=organization["name"],
                    type=organization["type"],
                    location=organization["location"],
                )
            )
        session.flush()
        for food in data["foods"]:
            session.add(
                FoodRecord(
                    **{
                        **food,
                        "id": UUID(food["id"]),
                        "donor_organization_id": UUID(food["donor_organization_id"]),
                        "quantity_kg": Decimal(food["quantity_kg"]),
                        "expiration_date": date.fromisoformat(food["expiration_date"]),
                    }
                )
            )
        session.flush()
        for request in data["requests"]:
            session.add(
                FoodRequestRecord(
                    **{
                        **request,
                        "id": UUID(request["id"]),
                        "food_id": UUID(request["food_id"]),
                        "recipient_organization_id": UUID(request["recipient_organization_id"]),
                        "quantity_kg": Decimal(request["quantity_kg"]),
                        "created_at": datetime.fromisoformat(request["created_at"]),
                    }
                )
            )
    report = analyze_dataset(ROOT / "data/demo.json")
    with Session(database) as session:
        metrics = SqlAlchemyMetricsRepository(session).metrics_summary(None, None)
        assert metrics.registered_food_kg == Decimal(report["registered_food_kg"])
        assert metrics.requests.requested_food_kg == Decimal(report["requested_food_kg"])
        assert metrics.requests.approved_food_kg == Decimal(report["approved_food_kg"])
        assert metrics.requests.total_requests == sum(report["request_counts"].values())
