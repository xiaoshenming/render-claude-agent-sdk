from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import requests


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    base_url: str
    api_key: str
    model: str
    max_tokens: int = 32_000
    temperature: float = 0.2
    timeout_seconds: int = 300
    max_attempts: int = 2
    retry_delay_seconds: float = 1.0


@dataclass(frozen=True, slots=True)
class GenerationResult:
    code: str
    input_tokens: int
    output_tokens: int
    elapsed_ms: int
    request_id: str
    model: str
    attempts: int


class GenerationFailed(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        input_tokens: int,
        output_tokens: int,
        elapsed_ms: int,
        attempts: int,
        model: str,
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.elapsed_ms = elapsed_ms
        self.attempts = attempts
        self.model = model
        super().__init__(message)


class GenerationClient:
    def __init__(
        self,
        config: GenerationConfig,
        *,
        transport: Callable[..., object] = requests.post,
    ) -> None:
        self._config = config
        self._transport = transport

    def generate(self, *, prompt: str, output_dir: Path) -> GenerationResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        attempts: list[dict] = []
        last_error: Exception | None = None
        total_input_tokens = 0
        total_output_tokens = 0
        for attempt in range(1, self._config.max_attempts + 1):
            request_id = str(uuid.uuid4())
            attempt_input = 0
            attempt_output = 0
            try:
                payload, raw_text = self._attempt(prompt, request_id)
                usage = payload.get("usage") if isinstance(payload, dict) else None
                usage = usage if isinstance(usage, dict) else {}
                attempt_input = _non_negative_int(usage.get("input_tokens"))
                attempt_output = _non_negative_int(usage.get("output_tokens"))
                total_input_tokens += attempt_input
                total_output_tokens += attempt_output
                (output_dir / f"response_attempt_{attempt:02d}.txt").write_text(
                    raw_text, encoding="utf-8"
                )
                code = extract_manim_code(raw_text)
                if "# === END ===" not in code:
                    raise ValueError("generated code is incomplete: missing END marker")
                attempts.append(
                    {
                        "attempt": attempt,
                        "request_id": request_id,
                        "ok": True,
                        "input_tokens": attempt_input,
                        "output_tokens": attempt_output,
                    }
                )
                result = GenerationResult(
                    code=code,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    elapsed_ms=round((time.perf_counter() - started) * 1_000),
                    request_id=request_id,
                    model=self._config.model,
                    attempts=attempt,
                )
                (output_dir / "response.txt").write_text(raw_text, encoding="utf-8")
                _write_json(
                    output_dir / "generation.json", asdict(result) | {"code": None}
                )
                _write_json(
                    output_dir / "generation_attempts.json", {"attempts": attempts}
                )
                return result
            except (requests.RequestException, ValueError) as error:
                last_error = error
                attempts.append(
                    {
                        "attempt": attempt,
                        "request_id": request_id,
                        "ok": False,
                        "input_tokens": attempt_input,
                        "output_tokens": attempt_output,
                        "error": f"{type(error).__name__}:{error}",
                    }
                )
                if attempt < self._config.max_attempts:
                    time.sleep(self._config.retry_delay_seconds)
        _write_json(output_dir / "generation_attempts.json", {"attempts": attempts})
        detail = last_error or RuntimeError("generation failed without an error")
        raise GenerationFailed(
            f"{type(detail).__name__}:{detail}",
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            elapsed_ms=round((time.perf_counter() - started) * 1_000),
            attempts=len(attempts),
            model=self._config.model,
        ) from detail

    def _attempt(self, prompt: str, request_id: str) -> tuple[dict, str]:
        response = self._transport(
            _messages_url(self._config.base_url),
            headers=_headers(self._config.api_key, request_id),
            json=_payload(self._config, prompt, request_id),
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        raw_text = _response_text(payload)
        return payload, raw_text


def extract_manim_code(response_text: str) -> str:
    blocks = re.findall(r"```(?:python)?\s*(.*?)```", response_text, re.I | re.S)
    candidates = blocks or [response_text]
    for candidate in sorted(candidates, key=len, reverse=True):
        code = candidate.strip()
        if "from manim import" in code and "class " in code:
            return code
    raise ValueError("response did not contain Manim source")


def _messages_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}/v1/messages"


def _headers(api_key: str, request_id: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "cache-control": "no-cache, no-store",
        "x-request-id": request_id,
    }


def _payload(config: GenerationConfig, prompt: str, request_id: str) -> dict:
    return {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "system": (
            f"Independent request {request_id}. Return complete Manim Python code only."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }


def _response_text(payload: object) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), list):
        raise ValueError("invalid Anthropic response")
    parts = [
        item.get("text", "")
        for item in payload["content"]
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    text = "".join(part for part in parts if isinstance(part, str)).strip()
    if not text:
        raise ValueError("Anthropic response contained no text")
    return text


def _non_negative_int(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
