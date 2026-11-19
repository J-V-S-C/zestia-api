from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.application.entities import (
    Organization,
    OrganizationType,
    VerificationStatus,
)
from app.application.errors import BusinessError, NotFound
from app.infrastructure.persistence.audit import record_event
from app.infrastructure.persistence.orm import (
    FoodRecord,
    FoodRequestRecord,
    OrganizationRecord,
)


def organization_from_record(record: OrganizationRecord) -> Organization:
    return Organization(
        record.id,
        record.owner_account_id,
        record.name,
        OrganizationType(record.type),
        record.location,
        record.deleted_at,
        VerificationStatus(record.verification_status),
    )


class SqlAlchemyOrganizationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_organization(
        self, organization_id: UUID, *, lock: bool = False, include_deleted: bool = False
    ) -> Organization:
        query = select(OrganizationRecord).where(OrganizationRecord.id == organization_id)
        if not include_deleted:
            query = query.where(OrganizationRecord.deleted_at.is_(None))
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        record = self.session.scalar(query)
        if record is None:
            raise NotFound("organization_not_found", "Organization does not exist.")
        return organization_from_record(record)

    def find_owned_organization(
        self, account_id: UUID, *, lock: bool = False
    ) -> Organization | None:
        query = select(OrganizationRecord).where(
            OrganizationRecord.owner_account_id == account_id,
            OrganizationRecord.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        record = self.session.scalar(query)
        return organization_from_record(record) if record else None

    def list_organizations(self, offset: int, limit: int) -> list[Organization]:
        records = self.session.scalars(
            select(OrganizationRecord)
            .where(OrganizationRecord.deleted_at.is_(None))
            .order_by(OrganizationRecord.name, OrganizationRecord.id)
            .offset(offset)
            .limit(limit)
        )
        return [organization_from_record(record) for record in records]

    def list_archived_organizations(
        self, account_id: UUID, offset: int, limit: int
    ) -> list[Organization]:
        records = self.session.scalars(
            select(OrganizationRecord)
            .where(
                OrganizationRecord.owner_account_id == account_id,
                OrganizationRecord.deleted_at.is_not(None),
            )
            .order_by(OrganizationRecord.name, OrganizationRecord.id)
            .offset(offset)
            .limit(limit)
        )
        return [organization_from_record(record) for record in records]

    def save_verification_evidence(self, organization_id: UUID, evidence: str | None) -> None:
        record = self.session.get(OrganizationRecord, organization_id)
        record.verification_evidence = evidence
        self.session.flush()

    def get_verification_evidence(self, organization_id: UUID) -> str | None:
        return self.session.get(OrganizationRecord, organization_id).verification_evidence

    def save_organization(self, organization: Organization) -> None:
        self.session.merge(OrganizationRecord(**asdict(organization)))
        self.session.flush()

    def delete_organization(self, organization: Organization) -> None:
        has_food = self.session.scalar(
            select(exists().where(FoodRecord.donor_organization_id == organization.id))
        )
        has_requests = self.session.scalar(
            select(exists().where(FoodRequestRecord.recipient_organization_id == organization.id))
        )
        if has_food or has_requests:
            raise BusinessError(
                "organization_in_use", "Organizations with associated records cannot be deleted."
            )
        record = self.session.get(OrganizationRecord, organization.id)
        record.deleted_at = datetime.now(UTC)
        self.session.flush()

    def record_event(
        self, account_id: UUID, action: str, organization_id: UUID | None = None, reason: str = ""
    ) -> None:
        record_event(self.session, account_id, action, organization_id, reason)
