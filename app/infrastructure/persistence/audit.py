from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.infrastructure.persistence.orm import LifecycleEventRecord


def record_event(
    session: Session,
    account_id: UUID,
    action: str,
    organization_id: UUID | None = None,
    reason: str = "",
) -> None:
    session.add(
        LifecycleEventRecord(
            id=uuid4(),
            account_id=account_id,
            organization_id=organization_id,
            action=action,
            reason=reason,
        )
    )
    session.flush()
