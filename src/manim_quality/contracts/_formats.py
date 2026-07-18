"""Canonical hash and callback URL formats for public contracts."""

from __future__ import annotations

import re
import unicodedata
from ipaddress import IPv6Address, ip_address
from urllib.parse import urlsplit

_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z", flags=re.ASCII)
_DNS_LABEL_PATTERN = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z",
    flags=re.ASCII | re.IGNORECASE,
)
_MAX_DNS_HOST_LENGTH = 253


def require_sha256(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must use canonical sha256:<64 lowercase hex> format"
        )
    return value


def require_optional_sha256(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return require_sha256(value, field_name)


def require_callback_url(value: object, field_name: str) -> str | None:
    """Validate callback URL structure only.

    DNS/IP resolution, redirect policy, and SSRF protection belong to the sender.
    """
    if value is None:
        return None
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string or null")
    if any(
        character.isspace() or unicodedata.category(character).startswith("C")
        for character in value
    ):
        raise ValueError(
            f"{field_name} must not contain whitespace or control characters"
        )
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        _ = parsed.port
    except ValueError as error:
        raise ValueError(f"{field_name} is not a valid URL") from error
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"{field_name} must use http or https")
    if not hostname:
        raise ValueError(f"{field_name} must include a hostname")
    if username is not None or password is not None:
        raise ValueError(f"{field_name} must not include username or password")
    _require_callback_host(hostname, parsed.netloc, field_name)
    return value


def _require_callback_host(hostname: str, netloc: str, field_name: str) -> None:
    bracketed = netloc.startswith("[")
    try:
        address = ip_address(hostname)
    except ValueError:
        if bracketed:
            raise ValueError(f"{field_name} bracketed hostname must be IPv6") from None
        _require_dns_hostname(hostname, field_name)
        return
    if isinstance(address, IPv6Address) and not bracketed:
        raise ValueError(f"{field_name} IPv6 hostname must use brackets")


def _require_dns_hostname(hostname: str, field_name: str) -> None:
    if len(hostname) > _MAX_DNS_HOST_LENGTH:
        raise ValueError(f"{field_name} DNS hostname is too long")
    labels = hostname.split(".")
    if any(_DNS_LABEL_PATTERN.fullmatch(label) is None for label in labels):
        raise ValueError(f"{field_name} contains an invalid DNS label")
