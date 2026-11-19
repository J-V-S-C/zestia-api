from typing import Protocol


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, password_hash: str | None) -> bool: ...


class RateLimiter(Protocol):
    def allow(self, keys: list[str], window_seconds: int, max_attempts: int) -> bool: ...
