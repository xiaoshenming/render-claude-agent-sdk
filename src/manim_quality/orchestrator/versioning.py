"""Independent version identities bound into every certificate."""

from dataclasses import dataclass

from ._model_validation import require_text


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    model_version: str
    prompt_version: str
    tool_version: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            require_text(getattr(self, name), name)

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class VersionBindings:
    config_version: str
    schema_version: str
    renderer_version: str
    environment_version: str
    logic_review: AgentIdentity
    logic_repair: AgentIdentity
    logic_verifier: AgentIdentity
    logic_validator_version: str
    layout_detector_version: str
    layout_policy_version: str
    layout_repair: AgentIdentity
    layout_recheck_version: str
    layout_semantic_verifier_version: str
    warning_policy_version: str
    gate_version: str

    def __post_init__(self) -> None:
        for name in (
            "config_version",
            "schema_version",
            "renderer_version",
            "environment_version",
            "logic_validator_version",
            "layout_detector_version",
            "layout_policy_version",
            "layout_recheck_version",
            "layout_semantic_verifier_version",
            "warning_policy_version",
            "gate_version",
        ):
            require_text(getattr(self, name), name)
        for name in (
            "logic_review",
            "logic_repair",
            "logic_verifier",
            "layout_repair",
        ):
            if not isinstance(getattr(self, name), AgentIdentity):
                raise TypeError(f"{name} must be an AgentIdentity")

    def to_dict(self) -> dict[str, object]:
        return {
            name: value.to_dict() if isinstance(value, AgentIdentity) else value
            for name, value in (
                (field_name, getattr(self, field_name))
                for field_name in self.__dataclass_fields__
            )
        }
