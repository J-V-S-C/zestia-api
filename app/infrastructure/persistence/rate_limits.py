from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.persistence.orm import RateLimitRecord


class SqlAlchemyRateLimiter:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def allow(self, keys: list[str], window_seconds: int, max_attempts: int) -> bool:
        now = datetime.now(UTC)
        allowed = True
        # Independent transaction preserves attempt counts after failed recovery.
        with self.sessions.begin() as session:
            for key in keys:
                session.execute(
                    insert(RateLimitRecord)
                    .values(key=key, attempts=0, window_start=now)
                    .on_conflict_do_nothing()
                )
                record = session.scalar(
                    select(RateLimitRecord).where(RateLimitRecord.key == key).with_for_update()
                )
                if record.window_start + timedelta(seconds=window_seconds) <= now:
                    record.window_start, record.attempts = now, 0
                record.attempts += 1
                if record.attempts > max_attempts:
                    allowed = False
                    break
        return allowed
