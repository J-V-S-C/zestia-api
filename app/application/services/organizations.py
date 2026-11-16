from dataclasses import replace
from uuid import UUID, uuid4

from app.application.entities import Organization, OrganizationType
from app.application.errors import BusinessError, Forbidden
from app.application.interfaces import OrganizationRepository


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

    def list(self, offset: int, limit: int) -> list[Organization]:
        return self.repository.list_organizations(offset, limit)

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
        updated = replace(organization, name=name, type=type, location=location)
        self.repository.save_organization(updated)
        return updated

    def delete(self, account_id: UUID, organization_id: UUID) -> None:
        organization = self.repository.get_organization(organization_id, lock=True)
        self._require_owner(account_id, organization)
        self.repository.delete_organization(organization)

    @staticmethod
    def _require_owner(account_id: UUID, organization: Organization) -> None:
        if account_id != organization.owner_account_id:
            raise Forbidden("not_owner", "Only the organization owner can change or delete it.")
