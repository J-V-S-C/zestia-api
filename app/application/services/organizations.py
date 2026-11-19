from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

from app.application.entities import Organization, OrganizationType, VerificationStatus
from app.application.errors import BusinessError, Forbidden, NotFound
from app.application.ports.repositories import OrganizationRepository


class OrganizationService:
    def __init__(self, repository: OrganizationRepository) -> None:
        self.repository = repository

    def create(
        self, account_id: UUID, name: str, type: OrganizationType, location: str
    ) -> Organization:
        if self.repository.find_owned_organization(account_id):
            raise BusinessError("organization_exists", "An account can own only one organization.")
        organization = Organization(uuid4(), account_id, name, type, location)
        self.repository.save_organization(organization)
        return organization

    def get(self, organization_id: UUID) -> Organization:
        return self.repository.get_organization(organization_id)

    def owned(self, account_id: UUID) -> Organization:
        organization = self.repository.find_owned_organization(account_id)
        if organization is None:
            raise NotFound("organization_not_found", "The account has no active organization.")
        return organization

    def list(self, offset: int, limit: int) -> list[Organization]:
        return self.repository.list_organizations(offset, limit)

    def archived(self, account_id: UUID, offset: int, limit: int) -> list[Organization]:
        return self.repository.list_archived_organizations(account_id, offset, limit)

    def update(
        self,
        account_id: UUID,
        organization_id: UUID,
        name: str,
        type: OrganizationType,
        location: str,
    ) -> Organization:
        organization = self.repository.get_organization(organization_id, lock=True)
        self._require_owner(account_id, organization)
        identity_changed = organization.name != name.strip() or organization.type != type
        status = organization.verification_status
        if identity_changed and status == VerificationStatus.VERIFIED:
            status = VerificationStatus.PENDING
        updated = replace(
            organization, name=name, type=type, location=location, verification_status=status
        )
        self.repository.save_organization(updated)
        if identity_changed:
            self.repository.save_verification_evidence(organization.id, None)
        return updated

    def delete(self, account_id: UUID, organization_id: UUID) -> None:
        organization = self.repository.get_organization(organization_id, lock=True)
        self._require_owner(account_id, organization)
        self.repository.delete_organization(organization)

    def restore(self, account_id: UUID, organization_id: UUID) -> Organization:
        organization = self.repository.get_organization(
            organization_id, lock=True, include_deleted=True
        )
        self._require_owner(account_id, organization)
        if organization.deleted_at is None:
            raise BusinessError("organization_active", "Organization is already active.")
        if self.repository.find_owned_organization(account_id):
            raise BusinessError(
                "organization_exists", "Archive the active organization before restoring another."
            )
        restored = replace(organization, deleted_at=None)
        self.repository.save_organization(restored)
        self.repository.record_event(account_id, "ORGANIZATION_RESTORED", organization_id)
        return restored

    @staticmethod
    def _require_owner(account_id: UUID, organization: Organization) -> None:
        if account_id != organization.owner_account_id:
            raise Forbidden("not_owner", "Only the organization owner can change or delete it.")
