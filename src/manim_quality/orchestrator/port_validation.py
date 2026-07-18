"""Fail-fast runtime validation for injected orchestration capabilities."""


def require_orchestration_ports(
    logic_review,
    logic_repair,
    logic_verify,
    layout_detect,
    layout_repair,
    layout_recheck,
    layout_semantic_verify,
    warning_policy,
    renderer,
) -> None:
    requirements = (
        ("logic_review", logic_review, ("assess",)),
        ("logic_repair", logic_repair, ("propose",)),
        ("logic_verify", logic_verify, ("verify",)),
        ("layout_detect", layout_detect, ("assess",)),
        ("layout_repair", layout_repair, ("propose",)),
        ("layout_recheck", layout_recheck, ("verify",)),
        ("layout_semantic_verify", layout_semantic_verify, ("verify",)),
        ("warning_policy", warning_policy, ("authorize",)),
        ("renderer", renderer, ("render", "bind")),
    )
    for port_name, component, operations in requirements:
        for operation in operations:
            if not callable(getattr(component, operation, None)):
                raise TypeError(f"{port_name}.{operation} must be callable")
