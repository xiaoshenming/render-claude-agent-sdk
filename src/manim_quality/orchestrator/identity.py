"""Immutable role and session identity for independent stage components."""

from dataclasses import dataclass
from enum import StrEnum

from ._model_validation import require_hash, require_text


class ComponentRole(StrEnum):
    LOGIC_REPAIR = "LOGIC_REPAIR"
    LOGIC_VERIFY = "LOGIC_VERIFY"
    LAYOUT_REPAIR = "LAYOUT_REPAIR"
    LAYOUT_RECHECK = "LAYOUT_RECHECK"
    LAYOUT_SEMANTIC_VERIFY = "LAYOUT_SEMANTIC_VERIFY"


@dataclass(frozen=True, slots=True)
class ComponentIdentity:
    role: ComponentRole
    component_id: str
    profile_hash: str
    session_scope: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, ComponentRole):
            raise TypeError("role must be a ComponentRole")
        require_text(self.component_id, "component_id")
        require_hash(self.profile_hash, "profile_hash")
        require_text(self.session_scope, "session_scope")

    def to_dict(self) -> dict[str, str]:
        return {
            "component_id": self.component_id,
            "profile_hash": self.profile_hash,
            "role": self.role.value,
            "session_scope": self.session_scope,
        }
