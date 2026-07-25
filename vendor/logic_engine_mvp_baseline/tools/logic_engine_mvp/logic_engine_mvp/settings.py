from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


DEFAULT_REVIEWER_BASE_URL = "https://api.deepseek.com"
DEFAULT_REVIEWER_MODEL = "deepseek-v4-flash"
DEFAULT_AGENT_BASE_URL = "https://ai.onegodtoken.top"
DEFAULT_AGENT_MODEL = "gemini-3.5-flash-high"


@dataclass(frozen=True)
class LlmConfig:
    role: str
    base_url: str
    api_key: str
    model: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    @property
    def masked_api_key(self) -> str:
        return mask_secret(self.api_key)

    def safe_dict(self) -> dict[str, str]:
        return {
            "role": self.role,
            "base_url": self.base_url,
            "model": self.model,
            "api_key": self.masked_api_key,
        }

    def __repr__(self) -> str:
        return (
            "LlmConfig("
            f"role={self.role!r}, base_url={self.base_url!r}, "
            f"api_key={self.masked_api_key!r}, model={self.model!r})"
        )


def load_reviewer_config(env: Mapping[str, str] | None = None) -> LlmConfig:
    values = os.environ if env is None else env
    api_key = _required(values, "LOGIC_REVIEWER_API_KEY")
    return LlmConfig(
        role="reviewer",
        base_url=values.get("LOGIC_REVIEWER_BASE_URL", DEFAULT_REVIEWER_BASE_URL),
        api_key=api_key,
        model=values.get("LOGIC_REVIEWER_MODEL", DEFAULT_REVIEWER_MODEL),
    )


def load_agent_config(env: Mapping[str, str] | None = None) -> LlmConfig:
    values = os.environ if env is None else env
    api_key = _required(values, "LOGIC_AGENT_API_KEY")
    return LlmConfig(
        role="agent",
        base_url=values.get("LOGIC_AGENT_BASE_URL", DEFAULT_AGENT_BASE_URL),
        api_key=api_key,
        model=values.get("LOGIC_AGENT_MODEL", DEFAULT_AGENT_MODEL),
    )


def mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]}"


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if not value:
        raise ValueError(f"missing required environment variable: {name}")
    return value
