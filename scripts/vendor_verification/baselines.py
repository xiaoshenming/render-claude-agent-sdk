"""Expected identities and test commands for frozen source baselines."""

BASELINES: dict[str, dict[str, object]] = {
    "quality_repair": {
        "archive_path": (
            "vendor/source_archives/quality_repair_source_handoff_20260711_platform1.tar.gz"
        ),
        "archive_prefix": "quality_repair_source_handoff_20260711_platform1",
        "materialized_root": ".vendor/quality_repair",
        "source_type": "tar.gz archive",
        "source_archive_sha256": (
            "90d0a55d14d54acee640645c0fd48ad37faa7e7be6c4a8585c4e73ce6865579c"
        ),
        "source_revision": "ae371aecd9cd258344c94ecdfa6a6cdd36417f5c",
        "compatibility_revision": "quality-platform.1",
        "content_identity": (
            "sha256:18083bc719d18c22fd5fee461db4d29f9e7d487531fba20a4e57fad2355d1d93"
        ),
        "claude_agent_sdk_version": "0.2.115",
        "manifest_path": "PAYLOAD_SHA256SUMS.txt",
        "manifest_sha256": (
            "18083bc719d18c22fd5fee461db4d29f9e7d487531fba20a4e57fad2355d1d93"
        ),
        "inventory_manifest_path": "SOURCE_MANIFEST.txt",
        "inventory_manifest_sha256": (
            "0be94d09ef133dad173550487585d0e5cbb3d23abf6f94b4a90b6a757c0cc03a"
        ),
        "metadata_files": ("PAYLOAD_SHA256SUMS.txt", "SOURCE_MANIFEST.txt"),
        "required_files": (
            "HANDOFF_README.md",
            "requirements-handoff.txt",
            "verify_handoff.sh",
            "libs/quality_repair/api.py",
            "libs/quality_repair/tests/test_api_e2e.py",
        ),
        "windows_test_command": (
            "$env:PYTHONPATH='.vendor\\quality_repair'; "
            ".\\.venv\\Scripts\\python.exe -m pytest "
            ".vendor\\quality_repair\\libs\\quality_repair\\tests "
            ".vendor\\quality_repair\\tools\\quality_repair_m0\\tests -q"
        ),
        "linux_test_command": (
            "PYTHONPATH=.vendor/quality_repair python3.11 -m pytest "
            "-p no:cacheprovider .vendor/quality_repair/libs/quality_repair/tests "
            ".vendor/quality_repair/tools/quality_repair_m0/tests -q"
        ),
    },
    "logic_self_audit_baseline": {
        "root": "vendor/logic_self_audit_baseline",
        "source_type": "untracked working-tree snapshot",
        "source_archive_sha256": None,
        "source_revision": None,
        "content_identity": (
            "sha256:e0f123e603231a2e4a8a533a81b4befeec4c4417b9755b9b244a14d453513412"
        ),
        "claude_agent_sdk_version": "0.2.110",
        "manifest_path": "SOURCE_MANIFEST.sha256",
        "manifest_sha256": (
            "e0f123e603231a2e4a8a533a81b4befeec4c4417b9755b9b244a14d453513412"
        ),
        "metadata_files": ("SOURCE_MANIFEST.sha256",),
        "required_files": (
            "app/workers/validation/code_validator.py",
            "app/workers/post_render_logic/sdk_runner.py",
            "tests/test_post_render_logic_pipeline.py",
            "tests/test_post_render_logic_claude_sdk.py",
        ),
        "windows_test_command": (
            "$env:PYTHONPATH='vendor\\logic_self_audit_baseline'; "
            ".\\.venv\\Scripts\\python.exe -m pytest "
            "vendor\\logic_self_audit_baseline\\tests -q"
        ),
        "linux_test_command": (
            "PYTHONPATH=vendor/logic_self_audit_baseline python3.11 -m pytest "
            "-p no:cacheprovider vendor/logic_self_audit_baseline/tests -q"
        ),
    },
    "logic_engine_mvp_baseline": {
        "root": "vendor/logic_engine_mvp_baseline",
        "source_type": "untracked working-tree snapshot",
        "source_archive_sha256": None,
        "source_revision": None,
        "content_identity": (
            "sha256:bfdcf809d69a125dfb5bd164a5ec16556b944be4d471f8b671009ce3f410149a"
        ),
        "claude_agent_sdk_version": (
            "not pinned; platform adapter verified with 0.2.115"
        ),
        "manifest_path": "SOURCE_MANIFEST.sha256",
        "manifest_sha256": (
            "bfdcf809d69a125dfb5bd164a5ec16556b944be4d471f8b671009ce3f410149a"
        ),
        "metadata_files": ("SOURCE_MANIFEST.sha256",),
        "required_files": (
            "tools/logic_engine_mvp/README.md",
            "tools/logic_engine_mvp/logic_engine_mvp/logic_facts.py",
            "tools/logic_engine_mvp/logic_engine_mvp/review_input.py",
            "tools/logic_engine_mvp/logic_engine_mvp/sdk_agent_runner.py",
            "tools/logic_engine_mvp/logic_engine_mvp/validator.py",
            "tools/logic_engine_mvp/logic_engine_mvp/verifier.py",
            "tools/logic_engine_mvp/tests/test_mutation_eval.py",
        ),
        "windows_test_command": (
            "$env:PYTHONPATH='vendor\\logic_engine_mvp_baseline'; "
            ".\\.venv\\Scripts\\python.exe -m pytest "
            "vendor\\logic_engine_mvp_baseline\\tools\\logic_engine_mvp\\tests -q"
        ),
        "linux_test_command": (
            "PYTHONPATH=vendor/logic_engine_mvp_baseline python3.11 -m pytest "
            "-p no:cacheprovider "
            "vendor/logic_engine_mvp_baseline/tools/logic_engine_mvp/tests -q"
        ),
    },
}
