from pwdlib import PasswordHash


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self.hasher = PasswordHash.recommended()
        self.dummy_hash = self.hasher.hash("unused-dummy-password")

    def hash(self, password: str) -> str:
        return self.hasher.hash(password)

    def verify(self, password: str, password_hash: str | None) -> bool:
        return self.hasher.verify(password, password_hash or self.dummy_hash)
