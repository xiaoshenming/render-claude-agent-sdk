"""Direct callback HTTP transport pinned to a validated destination IP."""

from __future__ import annotations

import socket
import ssl
from urllib.parse import urlsplit

from .security import ResolvedDestination


class PinnedHttpTransport:
    def __init__(
        self,
        *,
        socket_factory=socket.create_connection,
        ssl_context=None,
        timeout_seconds: float = 10,
    ) -> None:
        self._socket_factory = socket_factory
        self._ssl_context = ssl_context or ssl.create_default_context()
        self._timeout = timeout_seconds

    def send(
        self,
        destination: ResolvedDestination,
        body: bytes,
        headers: dict[str, str],
    ) -> int:
        parsed = urlsplit(destination.url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        selected_ip = destination.addresses[0]
        connection = self._socket_factory((selected_ip, port), self._timeout)
        try:
            if parsed.scheme == "https":
                connection = self._ssl_context.wrap_socket(
                    connection, server_hostname=destination.hostname
                )
            connection.sendall(
                _request_bytes(parsed, parsed.path, parsed.query, body, headers)
            )
            response = connection.recv(4096)
            return _status_code(response)
        finally:
            connection.close()


def _request_bytes(parsed, path, query, body, headers) -> bytes:
    target = path or "/"
    if query:
        target = f"{target}?{query}"
    lines = [
        f"POST {target} HTTP/1.1",
        f"Host: {_host_authority(parsed)}",
        f"Content-Length: {len(body)}",
        "Connection: close",
    ]
    for name, value in headers.items():
        if "\r" in name + value or "\n" in name + value:
            raise ValueError("callback header contains a newline")
        lines.append(f"{name}: {value}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


def _host_authority(parsed) -> str:
    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("callback URL has no hostname")
    authority = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if parsed.scheme == "https" else 80
    if parsed.port is not None and parsed.port != default_port:
        return f"{authority}:{parsed.port}"
    return authority


def _status_code(response: bytes) -> int:
    try:
        first_line = response.split(b"\r\n", 1)[0]
        return int(first_line.split(b" ", 2)[1])
    except (IndexError, ValueError) as error:
        raise RuntimeError("invalid callback HTTP response") from error
