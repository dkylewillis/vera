"""Public exception types raised by archive reads and writes."""


class DuplicateRecordError(ValueError):
    """Raised when add() receives an ID that already exists."""


class RecordNotFoundError(KeyError):
    """Raised when a requested chunk or attachment does not exist."""


class ReadOnlyError(PermissionError):
    """Raised when a write is attempted on a read-only database."""
