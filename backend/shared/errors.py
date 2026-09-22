"""
One error type, raised by every service, translated to HTTP in one place.

Services never build a status code or a response body themselves -- they raise
ApiError and backend/app.py turns it into JSON.
"""


class ApiError(Exception):
    """An error with a message that is safe to show the user."""

    def __init__(self, status_code: int, message: str, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.details = details


class MissingParams(ApiError):
    """A simulation cannot run until the caller supplies these parameters.

    The chat service turns this into a question rather than an error: the
    agent asks for missing numbers in conversation.
    """

    def __init__(self, needed: list, message: str = "More information needed."):
        super().__init__(422, message, {"needed": needed})
        self.needed = needed


class AuthError(ApiError):
    """Sign-in failed, or the caller is not allowed to do this."""

    def __init__(self, message: str = "Sign in to continue.", status_code: int = 401):
        super().__init__(status_code, message)
