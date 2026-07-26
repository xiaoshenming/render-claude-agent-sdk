"""Real provider tool_use smoke over httpx, Node, or ambient login."""

from __future__ import annotations

import json
import os
import subprocess

import httpx


def _provider_tool_smoke(model: str) -> dict[str, object]:
    base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip()
    if not api_key and not auth_token:
        if os.environ.get("ANTHROPIC_BASE_URL", "").strip():
            return {"ok": False, "error": "authentication missing"}
        return _provider_smoke_ambient(model)
    # Match the SDK's single-credential semantics: an API key travels as
    # x-api-key, a bearer token as Authorization; never send both.
    if api_key:
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    else:
        headers = {
            "authorization": f"Bearer {auth_token}",
            "anthropic-version": "2023-06-01",
        }
    payload = {
        "model": model,
        "max_tokens": 32,
        "messages": [{"role": "user", "content": "Call the health tool once."}],
        "tools": [
            {
                "name": "health",
                "description": "Return runtime health.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            }
        ],
        "tool_choice": {"type": "tool", "name": "health"},
    }
    try:
        response = httpx.post(
            f"{base}/v1/messages",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        value = response.json()
    except httpx.TransportError:
        # Some relays TLS-fingerprint-filter Python clients while serving
        # the Node-based SDK CLI just fine; retry the same real tool_use
        # smoke through Node before declaring the provider unreachable.
        return _provider_tool_smoke_node(base, headers, payload)
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {str(error)[:300]}"}
    return _tool_smoke_verdict(value)


def _tool_smoke_verdict(value: object) -> dict[str, object]:
    content = value.get("content") if isinstance(value, dict) else None
    used = any(
        isinstance(item, dict) and item.get("type") == "tool_use"
        for item in (content or [])
    )
    usage = value.get("usage") if isinstance(value, dict) else None
    return {"ok": used, "error": None if used else "tool_use missing", "usage": usage}


def _provider_tool_smoke_node(
    base: str,
    headers: dict[str, str],
    payload: dict[str, object],
) -> dict[str, object]:
    script = (
        "const [base, headers, payload] ="
        " JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "fetch(base + '/v1/messages',"
        " {method: 'POST', headers: {...headers, 'content-type':"
        " 'application/json'}, body: JSON.stringify(payload)})"
        ".then(r => r.text().then(t => console.log(JSON.stringify("
        "{status: r.status, body: t}))))"
        ".catch(e => { console.log(JSON.stringify({status: 0, body:"
        " String(e && e.cause ? e.cause : e)})); });"
    )
    result = subprocess.run(
        ["node", "-e", script],
        input=json.dumps([base, headers, payload]),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    try:
        reply = json.loads(result.stdout.strip().splitlines()[-1])
        if reply["status"] != 200:
            detail = str(reply["body"])[:300]
            return {"ok": False, "error": f"node smoke {reply['status']}: {detail}"}
        return _tool_smoke_verdict(json.loads(reply["body"]))
    except Exception as error:
        return {"ok": False, "error": f"node smoke failed: {error}"}


def _provider_smoke_ambient(model: str) -> dict[str, object]:
    """Real end-to-end auth check through the official login session."""

    argv = [
        "claude",
        "-p",
        "Reply with exactly: ok",
        "--model",
        model,
        "--output-format",
        "json",
        "--max-turns",
        "1",
    ]
    try:
        result = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "error": f"ambient smoke failed: {error}"}
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:300]
        return {"ok": False, "error": f"ambient smoke exit {result.returncode}: {detail}"}
    try:
        value = json.loads(result.stdout.strip().splitlines()[-1])
        return {
            "ok": not value.get("is_error", False),
            "error": None,
            "mode": "ambient_official_login",
            "usage": value.get("usage"),
        }
    except (ValueError, IndexError) as error:
        return {"ok": False, "error": f"ambient smoke bad output: {error}"}
