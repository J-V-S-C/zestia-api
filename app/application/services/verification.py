from dataclasses import replace
from typing import Protocol
from uuid import UUID

from app.application.entities import Account, AccountRole, Organization, VerificationStatus
from app.application.errors import BusinessError, Forbidden, InvalidInput
from app.application.interfaces import OrganizationRepository


class VerificationRepository(OrganizationRepository, Protocol):
    def save_verification_evidence(self, organization_id: UUID, evidence: str | None) -> None: ...
    def get_verification_evidence(self, organization_id: UUID) -> str | None: ...


class VerificationService:
    def __init__(self, repository: VerificationRepository) -> None:
        self.repository = repository

    def submit(self, account: Account, organization_id: UUID, evidence: str | None) -> Organization:
        evidence = evidence.strip()
        if not 20 <= len(evidence) <= 1000:
            raise InvalidInput("invalid_evidence", "Evidence must contain 20–1000 characters.")
        organization = self.repository.get_organization(organization_id, lock=True)
        if organization.owner_account_id != account.id:
            raise Forbidden("not_owner", "Only the organization owner can submit evidence.")
        if organization.verification_status in (
            VerificationStatus.SUSPENDED,
            VerificationStatus.VERIFIED,
        ):
            raise BusinessError(
                "review_unavailable", "Organization is already verified or suspended."
            )
        updated = replace(organization, verification_status=VerificationStatus.PENDING)
        self.repository.save_organization(updated)
        self.repository.save_verification_evidence(organization.id, evidence)
        self.repository.record_event(account.id, "VERIFICATION_SUBMITTED", organization.id)
        return updated

    def evidence(self, admin: Account, organization_id: UUID) -> str | None:
        self._admin(admin)
        self.repository.get_organization(organization_id)
        return self.repository.get_verification_evidence(organization_id)

    def review(
        self, admin: Account, organization_id: UUID, status: VerificationStatus, reason: str
    ) -> Organization:
        self._admin(admin)
        reason = reason.strip()
        if not 1 <= len(reason) <= 1000:
            raise InvalidInput("invalid_reason", "Review reason must contain 1–1000 characters.")
        organization = self.repository.get_organization(organization_id, lock=True)
        if admin.id == organization.owner_account_id:
            raise Forbidden("self_review", "Admins cannot review their own organization.")
        transitions = {
            VerificationStatus.PENDING: {VerificationStatus.VERIFIED, VerificationStatus.REJECTED},
            VerificationStatus.VERIFIED: {VerificationStatus.SUSPENDED},
            VerificationStatus.SUSPENDED: {VerificationStatus.PENDING},
            VerificationStatus.REJECTED: {VerificationStatus.PENDING},
        }
        if status not in transitions[organization.verification_status]:
            raise BusinessError(
                "invalid_review_transition", "Verification transition is not allowed."
            )
        if status == VerificationStatus.VERIFIED and not self.repository.get_verification_evidence(
            organization_id
        ):
            raise BusinessError(
                "evidence_required", "Evidence must be submitted before verification."
            )
        updated = replace(organization, verification_status=status)
        self.repository.save_organization(updated)
        self.repository.record_event(admin.id, f"VERIFICATION_{status}", organization_id, reason)
        return updated

    @staticmethod
    def _admin(account: Account) -> None:
        if account.role != AccountRole.ADMIN:
            raise Forbidden("admin_required", "Organization admin permission is required.")
