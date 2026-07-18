"""Expected fields rendered in the frozen-source provenance document."""

PROVENANCE_FIELDS = {
    "quality_repair": (
        ("Source type", "source_type"),
        ("Original archive SHA-256", "source_archive_sha256"),
        ("Reported source revision", "source_revision"),
        ("Content identity", "content_identity"),
        ("Claude Agent SDK version", "claude_agent_sdk_version"),
        ("File manifest SHA-256", "manifest_sha256"),
        ("Inventory manifest SHA-256", "inventory_manifest_sha256"),
    ),
    "logic_self_audit_baseline": (
        ("Source type", "source_type"),
        ("Original archive SHA-256", "source_archive_sha256"),
        ("Source revision", "source_revision"),
        ("Content identity", "content_identity"),
        ("Claude Agent SDK version", "claude_agent_sdk_version"),
        ("File manifest SHA-256", "manifest_sha256"),
    ),
    "logic_engine_mvp_baseline": (
        ("Source type", "source_type"),
        ("Original archive SHA-256", "source_archive_sha256"),
        ("Source revision", "source_revision"),
        ("Content identity", "content_identity"),
        ("Claude Agent SDK version", "claude_agent_sdk_version"),
        ("File manifest SHA-256", "manifest_sha256"),
    ),
}

NULL_PROVENANCE_VALUES = {
    ("logic_self_audit_baseline", "source_archive_sha256"): (
        "not applicable; this source was not an archive."
    ),
    ("logic_self_audit_baseline", "source_revision"): "none.",
    ("logic_engine_mvp_baseline", "source_archive_sha256"): (
        "not applicable; this source was not an archive."
    ),
    ("logic_engine_mvp_baseline", "source_revision"): "none.",
}
