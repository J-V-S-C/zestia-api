from typing import Protocol


class RecoveryDelivery(Protocol):
    def __call__(self, email: str, token: str) -> None: ...
