"""Errors shared by every engine that calls an external provider."""


class ProviderError(RuntimeError):
    """A sanitized provider failure suitable for saved research events."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
