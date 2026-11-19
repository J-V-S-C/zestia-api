"""Analyze the included synthetic dataset without a database, secrets or network access."""

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from app.application.entities import Food, FoodRequest, RequestStatus
from app.application.services.analysis import analyze_food_requests

ROOT = Path(__file__).resolve().parents[1]


def analyze_dataset(path: Path) -> dict:
    data = json.loads(path.read_text(), parse_float=Decimal)
    if data["source"]["kind"] != "synthetic":
        raise ValueError("This demonstration accepts explicitly synthetic data only.")
    organizations = {UUID(item["id"]) for item in data["organizations"]}
    foods = [
        Food(
            UUID(item["id"]),
            UUID(item["donor_organization_id"]),
            item["name"],
            item["category"],
            Decimal(item["quantity_kg"]),
            date.fromisoformat(item["expiration_date"]),
        )
        for item in data["foods"]
    ]
    listings = {food.id: food for food in foods}
    requests = [
        FoodRequest(
            UUID(item["id"]),
            UUID(item["food_id"]),
            listings[UUID(item["food_id"])].donor_organization_id,
            UUID(item["recipient_organization_id"]),
            Decimal(item["quantity_kg"]),
            RequestStatus(item["status"]),
            datetime.fromisoformat(item["created_at"]),
        )
        for item in data["requests"]
    ]
    if any(food.donor_organization_id not in organizations for food in foods) or any(
        request.recipient_organization_id not in organizations for request in requests
    ):
        raise ValueError("Food/request references an unknown organization.")
    return {
        "source": data["source"],
        **analyze_food_requests(foods, requests, date.fromisoformat(data["snapshot_date"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/demo.json")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = json.dumps(analyze_dataset(arguments.dataset), indent=2, ensure_ascii=False) + "\n"
    if arguments.output:
        arguments.output.write_text(report)
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
