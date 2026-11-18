from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.entities import (
    Account,
    AccountRole,
    Food,
    Organization,
    OrganizationType,
    VerificationStatus,
)
from app.application.errors import BusinessError, InvalidInput, NotFound
from app.infrastructure.models import (
    AccountRecord,
    AuthSessionRecord,
    FoodRecord,
    FoodRequestRecord,
    LifecycleEventRecord,
    OrganizationRecord,
    RecoveryRecord,
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


class SqlAlchemyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_account(self, account_id: UUID) -> Account | None:
        record = self.session.scalar(
            select(AccountRecord)
            .where(AccountRecord.id == account_id, AccountRecord.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (
            Account(
                record.id,
                record.email,
                record.password_hash,
                record.deleted_at,
                AccountRole(record.role),
            )
            if record
            else None
        )

    def record_event(
        self, account_id: UUID, action: str, organization_id: UUID | None = None, reason: str = ""
    ) -> None:
        self.session.add(
            LifecycleEventRecord(
                id=uuid4(),
                account_id=account_id,
                organization_id=organization_id,
                action=action,
                reason=reason,
            )
        )
        self.session.flush()

    def save_recovery(self, account_id: UUID, digest: str, expires_at: datetime) -> bool:
        account = self.session.scalar(
            select(AccountRecord)
            .where(AccountRecord.id == account_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if account.deleted_at is None:
            return False
        self.session.add(
            RecoveryRecord(account_id=account_id, token_hash=digest, expires_at=expires_at)
        )
        self.session.flush()
        return True

    def restore_account(self, digest: str) -> None:
        # Locate the owner first so every lifecycle operation locks account before token rows.
        candidate = self.session.get(RecoveryRecord, digest)
        if candidate is None:
            raise InvalidInput("invalid_recovery", "Recovery link is invalid or expired.")
        account = self.session.scalar(
            select(AccountRecord)
            .where(AccountRecord.id == candidate.account_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        token = self.session.scalar(
            select(RecoveryRecord)
            .where(RecoveryRecord.token_hash == digest)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = datetime.now(UTC)
        if account.deleted_at is None or token.used_at is not None or token.expires_at <= now:
            raise InvalidInput("invalid_recovery", "Recovery link is invalid or expired.")
        for recovery in self.session.scalars(
            select(RecoveryRecord).where(
                RecoveryRecord.account_id == account.id, RecoveryRecord.used_at.is_(None)
            )
        ):
            recovery.used_at = now
        self.revoke_all_sessions(account.id)
        account.deleted_at = None
        self.record_event(account.id, "ACCOUNT_RESTORED")
        self.session.flush()

    def save_session(self, account_id: UUID, token: str, expires_at: datetime) -> None:
        self.session.add(
            AuthSessionRecord(
                token_hash=sha256(token.encode()).hexdigest(),
                account_id=account_id,
                expires_at=expires_at,
            )
        )
        self.session.flush()

    def session_is_active(self, account_id: UUID, token: str) -> bool:
        record = self.session.get(AuthSessionRecord, sha256(token.encode()).hexdigest())
        return bool(
            record
            and record.account_id == account_id
            and record.revoked_at is None
            and record.expires_at > datetime.now(UTC)
        )

    def revoke_session(self, token: str) -> None:
        record = self.session.get(AuthSessionRecord, sha256(token.encode()).hexdigest())
        record.revoked_at = datetime.now(UTC)
        self.session.flush()

    def revoke_all_sessions(self, account_id: UUID) -> None:
        for record in self.session.scalars(
            select(AuthSessionRecord).where(
                AuthSessionRecord.account_id == account_id, AuthSessionRecord.revoked_at.is_(None)
            )
        ):
            record.revoked_at = datetime.now(UTC)
        self.session.flush()

    def find_account(self, email: str) -> Account | None:
        record = self.session.scalar(select(AccountRecord).where(AccountRecord.email == email))
        return (
            Account(
                record.id,
                record.email,
                record.password_hash,
                record.deleted_at,
                AccountRole(record.role),
            )
            if record
            else None
        )

    def save_account(self, account: Account) -> None:
        self.session.add(AccountRecord(**asdict(account)))
        self.session.flush()

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

    def delete_account(self, account_id: UUID) -> None:
        organization = self.find_owned_organization(account_id, lock=True)
        if organization is not None:
            self.delete_organization(organization)
        record = self.session.get(AccountRecord, account_id)
        record.deleted_at = datetime.now(UTC)
        self.revoke_all_sessions(account_id)
        self.session.flush()

    def save_food(self, food: Food) -> None:
        self.session.merge(FoodRecord(**asdict(food)))
        self.session.flush()

    def get_food(self, food_id: UUID, *, lock: bool = False) -> Food:
        query = select(FoodRecord).where(FoodRecord.id == food_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        record = self.session.scalar(query)
        if record is None:
            raise NotFound("food_not_found", "Food does not exist.")
        return food_from_record(record)

    def list_foods(
        self, offset: int, limit: int, donor_organization_id: UUID | None = None
    ) -> list[Food]:
        query = select(FoodRecord)
        if donor_organization_id is not None:
            query = query.where(FoodRecord.donor_organization_id == donor_organization_id)
        records = self.session.scalars(
            query.order_by(FoodRecord.name, FoodRecord.id).offset(offset).limit(limit)
        )
        return [food_from_record(record) for record in records]

    def approved_food_quantity(self, food_id: UUID) -> Decimal:
        return self.session.scalar(
            select(func.coalesce(func.sum(FoodRequestRecord.quantity_kg), 0)).where(
                FoodRequestRecord.food_id == food_id, FoodRequestRecord.status == "APPROVED"
            )
        )

    def delete_food(self, food: Food) -> None:
        record = self.session.get(FoodRecord, food.id)
        self.session.delete(record)
        try:
            self.session.flush()
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == "23503":
                raise BusinessError(
                    "food_in_use", "Food with associated requests cannot be deleted."
                ) from error
            raise


def food_from_record(record: FoodRecord) -> Food:
    return Food(
        record.id,
        record.donor_organization_id,
        record.name,
        record.category,
        record.quantity_kg,
        record.expiration_date,
    )
