"""Immutable worker outcomes."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobOutcome:
    callback_body: bytes | None = None

    def __post_init__(self) -> None:
        if self.callback_body is not None and not isinstance(self.callback_body, bytes):
            raise TypeError("callback_body must be bytes or None")

    @classmethod
    def completed(cls, callback_body: bytes | None = None) -> "JobOutcome":
        return cls(callback_body)
