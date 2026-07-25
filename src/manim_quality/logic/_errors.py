"""Logic evidence and review boundary errors."""


class EvidenceBuildError(RuntimeError):
    pass


class ReviewOutputValidationError(ValueError):
    """Model output is structurally or referentially correctable."""


class ReviewBindingInvariantError(RuntimeError):
    """Trusted evidence or binder invariants are broken."""
