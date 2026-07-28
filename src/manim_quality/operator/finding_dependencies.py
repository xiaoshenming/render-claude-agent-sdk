"""Finding graph validation independent from revision transition policy."""

from collections.abc import Mapping

from .models import Finding


def validate_finding_dependencies(
    existing: Mapping[str, Finding],
    additions: Mapping[str, Finding],
) -> None:
    combined = {**existing, **additions}
    for item in additions.values():
        if item.finding_id in item.depends_on_finding_ids:
            raise ValueError("finding dependency cycle contains itself")
        missing = set(item.depends_on_finding_ids) - set(combined)
        if missing:
            raise ValueError(
                "finding dependencies are unknown: " + ", ".join(sorted(missing))
            )
    for finding_id in additions:
        _visit(finding_id, combined, set(), set())


def _visit(
    finding_id: str,
    findings: Mapping[str, Finding],
    visiting: set[str],
    visited: set[str],
) -> None:
    if finding_id in visited:
        return
    if finding_id in visiting:
        raise ValueError("finding dependency cycle detected")
    visiting.add(finding_id)
    for dependency in findings[finding_id].depends_on_finding_ids:
        _visit(dependency, findings, visiting, visited)
    visiting.remove(finding_id)
    visited.add(finding_id)
