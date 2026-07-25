"""Content-addressed local artifact storage."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from manim_quality.revisions.fingerprint import sha256_bytes

_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ArtifactError(RuntimeError):
    """Base class for artifact integrity failures."""


class ArtifactHashMismatch(ArtifactError):
    """Raised when content differs from a caller's expected identity."""


class ArtifactCorruption(ArtifactError):
    """Raised when stored bytes no longer match their identity."""


class InvalidArtifactReference(ArtifactError):
    """Raised when a reference does not address its computed digest path."""


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    uri: str
    hash: str
    size: int
    media_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.uri, str) or not self.uri:
            raise ValueError("uri must be a non-empty string")
        _require_hash(self.hash, "hash")
        if (
            isinstance(self.size, bool)
            or not isinstance(self.size, int)
            or self.size < 0
        ):
            raise ValueError("size must be a non-negative integer")
        _require_media_type(self.media_type)


@runtime_checkable
class ArtifactStore(Protocol):
    def put(
        self,
        content: bytes,
        *,
        media_type: str,
        expected_hash: str | None = None,
    ) -> ArtifactRef: ...

    def get(self, artifact: ArtifactRef) -> bytes: ...


class LocalArtifactStore:
    """Filesystem adapter that publishes immutable artifacts atomically."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()

    def put(
        self,
        content: bytes,
        *,
        media_type: str,
        expected_hash: str | None = None,
    ) -> ArtifactRef:
        _require_media_type(media_type)
        digest = sha256_bytes(content)
        if expected_hash is not None:
            _require_hash(expected_hash, "expected_hash")
            if digest != expected_hash:
                raise ArtifactHashMismatch(
                    f"expected hash {expected_hash}, computed {digest}"
                )
        target = self._target(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            self._verify_file(target, digest, len(content))
        else:
            self._write_once(target, content, digest)
        return self._reference(target, digest, len(content), media_type)

    def get(self, artifact: ArtifactRef) -> bytes:
        if not isinstance(artifact, ArtifactRef):
            raise TypeError("artifact must be an ArtifactRef")
        target = self._target(artifact.hash)
        if artifact.uri != target.as_uri():
            raise InvalidArtifactReference(
                "artifact URI does not match the computed digest path"
            )
        try:
            content = target.read_bytes()
        except OSError as error:
            raise ArtifactCorruption(f"artifact cannot be read: {target}") from error
        self._verify_content(content, artifact.hash, artifact.size)
        return content

    def _target(self, digest: str) -> Path:
        _require_hash(digest, "digest")
        hex_digest = digest.removeprefix("sha256:")
        target = self._root / "sha256" / hex_digest[:2] / hex_digest
        if not target.resolve(strict=False).is_relative_to(self._root):
            raise InvalidArtifactReference("computed digest path escapes store root")
        return target

    def _write_once(self, target: Path, content: bytes, digest: str) -> None:
        descriptor, temp_name = tempfile.mkstemp(prefix=".artifact-", dir=target.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temp_path, target)
            except FileExistsError:
                self._verify_file(target, digest, len(content))
        finally:
            temp_path.unlink(missing_ok=True)

    def _verify_file(self, path: Path, digest: str, size: int) -> None:
        if path.is_symlink():
            raise ArtifactCorruption(f"artifact content does not match {digest}")
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ArtifactCorruption(f"artifact cannot be read: {path}") from error
        self._verify_content(content, digest, size)

    @staticmethod
    def _verify_content(content: bytes, digest: str, size: int) -> None:
        if len(content) != size or sha256_bytes(content) != digest:
            raise ArtifactCorruption(f"artifact content does not match {digest}")

    @staticmethod
    def _reference(
        target: Path, digest: str, size: int, media_type: str
    ) -> ArtifactRef:
        return ArtifactRef(
            uri=target.as_uri(),
            hash=digest,
            size=size,
            media_type=media_type,
        )


def _require_hash(value: object, name: str) -> str:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical SHA-256 hash")
    return value


def _require_media_type(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("media_type must be a non-empty string")
    return value
