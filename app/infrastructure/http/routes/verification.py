from uuid import UUID

from fastapi import APIRouter

from app.infrastructure.http.authentication import AccountDependency
from app.infrastructure.http.dtos import (
    OrganizationResponse,
    VerificationDecision,
    VerificationSubmission,
)
from app.infrastructure.http.providers import VerificationDependency

router = APIRouter()


@router.post(
    "/organizations/{organization_id}/verification",
    response_model=OrganizationResponse,
    tags=["verification"],
)
def submit_verification(
    organization_id: UUID,
    payload: VerificationSubmission,
    account: AccountDependency,
    service: VerificationDependency,
):
    return OrganizationResponse.model_validate(
        service.submit(account, organization_id, payload.evidence)
    )


@router.get("/organizations/{organization_id}/verification", tags=["verification"])
def get_verification(
    organization_id: UUID, account: AccountDependency, service: VerificationDependency
):
    return {"evidence": service.evidence(account, organization_id)}


@router.post(
    "/organizations/{organization_id}/verification/review",
    response_model=OrganizationResponse,
    tags=["verification"],
)
def review_verification(
    organization_id: UUID,
    payload: VerificationDecision,
    account: AccountDependency,
    service: VerificationDependency,
):
    return OrganizationResponse.model_validate(
        service.review(account, organization_id, payload.status, payload.reason)
    )
