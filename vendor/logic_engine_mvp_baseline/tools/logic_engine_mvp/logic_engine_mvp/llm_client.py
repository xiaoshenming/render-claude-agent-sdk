from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.request import Request

import requests

from .settings import LlmConfig


Transport = Callable[[Request, int], bytes]


@dataclass(frozen=True)
class LlmResponse:
    content: str
    usage: dict[str, Any]
    raw: dict[str, Any]


def chat_completion(
    config: LlmConfig,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0,
    timeout: int = 60,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    transport: Transport | None = None,
) -> LlmResponse:
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if response_format is not None:
        payload["response_format"] = response_format
    request = Request(
        f"{config.base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    raw_bytes = _default_transport(request, timeout) if transport is None else transport(request, timeout)
    raw = json.loads(raw_bytes.decode("utf-8"))
    choices = raw.get("choices") or []
    if not choices:
        raise ValueError("LLM response contains no choices")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str):
        raise ValueError("LLM response message content is not text")
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    return LlmResponse(content=content, usage=usage, raw=raw)


def _default_transport(request: Request, timeout: int) -> bytes:
    response = None
    for attempt in range(3):
        try:
            response = requests.post(
                request.full_url,
                data=request.data,
                headers=dict(request.header_items()),
                timeout=timeout,
            )
            break
        except requests.exceptions.RequestException:
            if attempt == 2:
                raise
            time.sleep(0.25 * (attempt + 1))
    if response is None:
        raise RuntimeError("request transport did not return a response")
    response.raise_for_status()
    return response.content
