"""Quality Operator session state and scope errors."""


class QualitySessionError(RuntimeError):
    pass


class InvalidSessionTransition(QualitySessionError):
    pass


class ProblemLockViolation(QualitySessionError):
    pass


class DuplicatePatch(QualitySessionError):
    pass


class ScopeViolation(QualitySessionError):
    pass
