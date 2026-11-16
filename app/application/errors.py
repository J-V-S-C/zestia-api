class BusinessError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class InvalidInput(BusinessError):
    pass


class NotFound(BusinessError):
    pass


class Forbidden(BusinessError):
    pass


class Unauthenticated(BusinessError):
    pass
