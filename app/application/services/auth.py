from uuid import UUID, uuid4

from app.application.entities import Account
from app.application.errors import BusinessError, InvalidInput, Unauthenticated
from app.application.interfaces import AccountRepository, PasswordHasher


class AuthenticationService:
    def __init__(self, repository: AccountRepository, hasher: PasswordHasher) -> None:
        self.repository = repository
        self.hasher = hasher

    def register(self, email: str, password: str) -> Account:
        if not 8 <= len(password) <= 128:
            raise InvalidInput("invalid_password", "Password must contain 8–128 characters.")
        email = email.strip().casefold()
        if self.repository.find_account(email):
            raise BusinessError("email_registered", "Email is already registered.")
        account = Account(uuid4(), email, self.hasher.hash(password))
        self.repository.save_account(account)
        return account

    def close(self, account_id: UUID) -> None:
        self.repository.delete_account(account_id)

    def login(self, email: str, password: str) -> Account:
        account = self.repository.find_account(email.strip().casefold())
        valid = self.hasher.verify(password, account.password_hash if account else None)
        if account is None or account.deleted_at is not None or not valid:
            raise Unauthenticated("invalid_credentials", "Email or password is incorrect.")
        return account
