"""Store-neutral service-delivery persistence errors."""

from manim_quality.revisions.store import RepositoryError


class IntakeConflict(RepositoryError):
    pass


class IntakeQuotaExceeded(RepositoryError):
    pass


class IntakeTransactionError(RepositoryError):
    pass


class SubmissionNotFound(RepositoryError):
    pass


class LeaseConflict(RepositoryError):
    pass


class QueueItemNotFound(RepositoryError):
    pass
