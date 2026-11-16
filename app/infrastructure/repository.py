from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.entities import Account, Organization, OrganizationType
from app.application.errors import BusinessError, NotFound
from app.infrastructure.models import AccountRecord, OrganizationRecord


def organization_from_record(record: OrganizationRecord) -> Organization:
    return Organization(
        record.id,
        record.owner_account_id,
        record.name,
        OrganizationType(record.type),
        record.location,
    )


class SqlAlchemyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_account(self, account_id: UUID) -> Account | None:
        record = self.session.get(AccountRecord, account_id)
        return Account(record.id, record.email, record.password_hash) if record else None

    def find_account(self, email: str) -> Account | None:
        record = self.session.scalar(select(AccountRecord).where(AccountRecord.email == email))
        return Account(record.id, record.email, record.password_hash) if record else None

    def save_account(self, account: Account) -> None:
        self.session.add(AccountRecord(**asdict(account)))
        self.session.flush()

    def get_organization(self, organization_id: UUID, *, lock: bool = False) -> Organization:
        query = select(OrganizationRecord).where(OrganizationRecord.id == organization_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        record = self.session.scalar(query)
        if record is None:
            raise NotFound("organization_not_found", "Organization does not exist.")
        return organization_from_record(record)

    def find_owned_organization(self, account_id: UUID) -> Organization | None:
        record = self.session.scalar(
            select(OrganizationRecord).where(OrganizationRecord.owner_account_id == account_id)
        )
        return organization_from_record(record) if record else None

    def list_organizations(self, offset: int, limit: int) -> list[Organization]:
        records = self.session.scalars(
            select(OrganizationRecord)
            .order_by(OrganizationRecord.name, OrganizationRecord.id)
            .offset(offset)
            .limit(limit)
        )
        return [organization_from_record(record) for record in records]

    def save_organization(self, organization: Organization) -> None:
        self.session.merge(OrganizationRecord(**asdict(organization)))
        self.session.flush()

    def delete_organization(self, organization: Organization) -> None:
        record = self.session.get(OrganizationRecord, organization.id)
        self.session.delete(record)
        try:
            self.session.flush()
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == "23503":
                raise BusinessError(
                    "organization_in_use",
                    "Organizations with associated records cannot be deleted.",
                ) from error
            raise
