"""Ownership rules for a Quality Operator artifact root."""

from pathlib import Path

_OWNED_RUNTIME_DIRECTORIES = {"agent_runtime", "acceptance_runtime"}
_PREEXISTING_LOG_FILES = {"usage-events.jsonl"}


def validate_existing_root(target: Path) -> None:
    if not target.exists():
        return
    unknown = {
        item.name for item in target.iterdir() if not _is_owned_existing_item(item)
    }
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"artifact root has unknown existing content: {names}")


def _is_owned_existing_item(item: Path) -> bool:
    if item.name in _OWNED_RUNTIME_DIRECTORIES:
        return item.is_dir()
    if item.name != "logs" or not item.is_dir():
        return False
    return all(
        child.name in _PREEXISTING_LOG_FILES and child.is_file()
        for child in item.iterdir()
    )
