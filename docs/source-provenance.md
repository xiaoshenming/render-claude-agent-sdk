# Frozen Source Provenance

This repository keeps both source baselines as evidence-only inputs. Platform
code must use adapters and must not import either baseline into
`src/manim_quality`.

## quality_repair

- Source type: `tar.gz archive`
- Original archive: `vendor/source_archives/quality_repair_source_handoff_20260711_platform1.tar.gz`
- Original archive SHA-256: `7af3fb512fe8ddf08da1f1687e7f0fdd0f5b4741a9ac4f17612987a35e02d6c7`
- Reported source revision: `ae371aecd9cd258344c94ecdfa6a6cdd36417f5c`
- Compatibility revision: `quality-platform.1`
- Content identity: `sha256:658bad46d52c87b3cb991284c101b43ee8a741c35181845ea983aa5301393c54`
- Claude Agent SDK version: `0.2.115`
- Frozen archive: `vendor/source_archives/quality_repair_source_handoff_20260711_platform1.tar.gz`
- Materialized root: `.vendor/quality_repair` (generated and Git-ignored)
- File manifest: `PAYLOAD_SHA256SUMS.txt` inside the frozen archive
- File manifest SHA-256: `658bad46d52c87b3cb991284c101b43ee8a741c35181845ea983aa5301393c54`
- Inventory manifest: `SOURCE_MANIFEST.txt` inside the frozen archive
- Inventory manifest SHA-256: `0be94d09ef133dad173550487585d0e5cbb3d23abf6f94b4a90b6a757c0cc03a`

The active baseline is a minimal compatibility release derived from upstream
archive SHA-256
`53357fc785cf8896c6ad0878ca68e9a0713114a47efc9eadbdc2cdd05f524221`
at revision `ae371aecd9cd258344c94ecdfa6a6cdd36417f5c`. It adds only the public
`candidate_mode` contract and SDK `task_budget` wiring; the upstream archive is
retained unchanged beside it for provenance.

The verifier checks the active archive's
archive hash, safe member paths, both manifests, all 116 payload hashes, required
files, source revision and SDK pin without extracting it. The materializer then
removes the outer `quality_repair_source_handoff_20260711_platform1` directory and writes
the verified payload to a fresh ignored target. The revision above is a source
claim preserved from `HANDOFF_README.md`; it is not a commit created or inferred
by this repository.

Materialize once before running payload tests or the future overlap adapter:

```powershell
.\.venv\Scripts\python.exe scripts\materialize_quality_repair.py
```

Windows payload command (use the isolated reproduction block below for the
reported Windows result):

```powershell
$env:PYTHONPATH='.vendor\quality_repair'; .\.venv\Scripts\python.exe -m pytest .vendor\quality_repair\libs\quality_repair\tests .vendor\quality_repair\tools\quality_repair_m0\tests -q
```

Linux frozen test command:

```bash
PYTHONPATH=.vendor/quality_repair python3.11 -m pytest -p no:cacheprovider .vendor/quality_repair/libs/quality_repair/tests .vendor/quality_repair/tools/quality_repair_m0/tests -q
```

## logic_self_audit_baseline

- Source type: `untracked working-tree snapshot`
- Original directory: `C:\Users\Admin\Desktop\shuxuepai\apps\render`
- Original archive SHA-256: not applicable; this source was not an archive.
- Source revision: none.
- Content identity: `sha256:e0f123e603231a2e4a8a533a81b4befeec4c4417b9755b9b244a14d453513412`
- Claude Agent SDK version: `0.2.110`
- Frozen root: `vendor/logic_self_audit_baseline`
- File manifest: `vendor/logic_self_audit_baseline/SOURCE_MANIFEST.sha256`
- File manifest SHA-256: `e0f123e603231a2e4a8a533a81b4befeec4c4417b9755b9b244a14d453513412`

The ten prototype files, two required legacy validation dependency files, and
two requested tests were untracked in the source working tree. The prototype
and tests were byte-identical to the dated handoff directory at
`C:\Users\Admin\Desktop\逻辑工具\logic_self_audit_agent_handoff_20260709`.
No Git revision is claimed for these files. The two validation files are copied
unchanged because `evidence.py` imports `app.workers.validation.code_validator`;
without them the old import layout cannot collect independently. The manifest
hash is the content identity substitute; the unrelated repository HEAD is not
used as provenance.

Windows logic command (also repeated as a self-contained block below):

```powershell
$env:PYTHONPATH='vendor\logic_self_audit_baseline'; .\.venv\Scripts\python.exe -m pytest vendor\logic_self_audit_baseline\tests -q
```

Linux frozen test command:

```bash
PYTHONPATH=vendor/logic_self_audit_baseline python3.11 -m pytest -p no:cacheprovider vendor/logic_self_audit_baseline/tests -q
```

Only these two copied files are baseline tests, and they contain 10 collected
tests. The previous `27 passed` handoff statement also counted a separate logic
engine source line. That later source is now frozen independently below rather
than being attributed to this handoff.

## logic_engine_mvp_baseline

- Source type: `untracked working-tree snapshot`
- Original directory: `C:\Users\Admin\Desktop\shuxuepai\tools\logic_engine_mvp`
- Original archive SHA-256: not applicable; this source was not an archive.
- Source revision: none.
- Content identity: `sha256:bfdcf809d69a125dfb5bd164a5ec16556b944be4d471f8b671009ce3f410149a`
- Claude Agent SDK version: `not pinned; platform adapter verified with 0.2.115`
- Frozen root: `vendor/logic_engine_mvp_baseline`
- File manifest: `vendor/logic_engine_mvp_baseline/SOURCE_MANIFEST.sha256`
- File manifest SHA-256: `bfdcf809d69a125dfb5bd164a5ec16556b944be4d471f8b671009ce3f410149a`

The source directory is untracked in its host repository, so no Git revision is
claimed. The frozen snapshot contains 33 source, test, README and example files;
`__pycache__`, `.pytest_cache`, `.pyc` and `.pyo` files are excluded. This source
is kept separate from `logic_self_audit_baseline` so later deterministic facts,
review input, verifier, validator and SDK repair behavior cannot be mistaken for
the earlier self-audit handoff.

Windows frozen test command:

```powershell
$env:PYTHONPATH='vendor\logic_engine_mvp_baseline'; .\.venv\Scripts\python.exe -m pytest vendor\logic_engine_mvp_baseline\tools\logic_engine_mvp\tests -q
```

Linux frozen test command:

```bash
PYTHONPATH=vendor/logic_engine_mvp_baseline python3.11 -m pytest -p no:cacheprovider vendor/logic_engine_mvp_baseline/tools/logic_engine_mvp/tests -q
```

## Windows local verification

Executed on Windows with the repository's Python 3.11.14 environment:

- Logic baseline: `10 passed` from the two copied test files.
- Logic engine MVP baseline: `11 passed` from the separately frozen source.
- Logic engine anti-hardcoding scan: `27 files`, `0 findings`.
- Overlap isolated full set: `236 passed, 6 failed, 14 warnings`.
- Overlap Windows core: `236 passed, 6 deselected, 14 warnings`.

The isolated overlap run set `QUALITY_REPAIR_SDK_ENV` to a nonexistent path so
the tests could not read the host's persistent SDK configuration. An earlier
unisolated run produced `228 passed, 14 failed`; eight extra failures came from
the host SDK env file and are not frozen-source results.

The six deselected Windows tests are:

```text
test_agent_runner_env.py::test_runner_loads_private_persistent_sdk_env
test_agent_runner_env.py::test_runner_private_env_overrides_inherited_sdk_env
test_agent_runner_env.py::test_runner_ignores_private_auth_token_value
test_agent_runner_sdk.py::test_runner_uses_private_env_model_without_leaking_to_child_env
test_agent_runner_sdk.py::test_runner_sdk_options_disable_subagents
test_runner_workspace.py::test_mirror_workspace_files_exposes_only_sdk_inputs
```

The first five depend on POSIX `chmod(0600)` semantics; the last requires
creating symlinks without Windows developer-mode or administrator privileges.
The warnings are frozen invalid-escape deprecations in generated contract test
inputs. No source behavior was changed. These tests use fake SDK query
functions and make no model or network calls.

### Complete Windows PowerShell commands

The full overlap command is intentionally expected to exit nonzero on native
Windows because the six platform-only tests fail there. The unique nonexistent
SDK env path prevents host configuration from affecting the result.

```powershell
.\.venv\Scripts\python.exe scripts\materialize_quality_repair.py
$env:PYTHONPATH = '.vendor\quality_repair'
$env:QUALITY_REPAIR_SDK_ENV = Join-Path $env:TEMP `
  ('missing-sdk-env-' + [guid]::NewGuid().ToString('N'))
$overlapTests = @(
  '.vendor\quality_repair\libs\quality_repair\tests'
  '.vendor\quality_repair\tools\quality_repair_m0\tests'
)
& .\.venv\Scripts\python.exe -m pytest @overlapTests -q
```

Expected count: `236 passed, 6 failed, 14 warnings`.

The Windows core command deselects exactly those six platform-only tests:

```powershell
$env:PYTHONPATH = '.vendor\quality_repair'
$env:QUALITY_REPAIR_SDK_ENV = Join-Path $env:TEMP `
  ('missing-sdk-env-' + [guid]::NewGuid().ToString('N'))
$overlapTests = @(
  '.vendor\quality_repair\libs\quality_repair\tests'
  '.vendor\quality_repair\tools\quality_repair_m0\tests'
)
$coreDeselects = @(
  '--deselect=.vendor/quality_repair/libs/quality_repair/tests/test_agent_runner_env.py::test_runner_loads_private_persistent_sdk_env'
  '--deselect=.vendor/quality_repair/libs/quality_repair/tests/test_agent_runner_env.py::test_runner_private_env_overrides_inherited_sdk_env'
  '--deselect=.vendor/quality_repair/libs/quality_repair/tests/test_agent_runner_env.py::test_runner_ignores_private_auth_token_value'
  '--deselect=.vendor/quality_repair/libs/quality_repair/tests/test_agent_runner_sdk.py::test_runner_uses_private_env_model_without_leaking_to_child_env'
  '--deselect=.vendor/quality_repair/libs/quality_repair/tests/test_agent_runner_sdk.py::test_runner_sdk_options_disable_subagents'
  '--deselect=.vendor/quality_repair/libs/quality_repair/tests/test_runner_workspace.py::test_mirror_workspace_files_exposes_only_sdk_inputs'
)
& .\.venv\Scripts\python.exe -m pytest @overlapTests @coreDeselects -q
```

Expected count: `236 passed, 6 deselected, 14 warnings`.

The logic baseline command is independent of the overlap commands:

```powershell
$env:PYTHONPATH = 'vendor\logic_self_audit_baseline'
& .\.venv\Scripts\python.exe -m pytest `
  vendor\logic_self_audit_baseline\tests -q
```

Expected count: `10 passed`.

## Secret scan evidence

The Task 02 working tree received a high-confidence offline secret scan with
`0 matches`. The scanned categories were known token and private-key formats,
sensitive filenames such as `.env`, PEM/key and private-key files, and long
credential assignments. The scan covered the workspace while excluding `.git`
and `.venv`; it did not print environment variable values.

## Linux / Python 3.11 authority

Ubuntu with Python 3.11 is authoritative for the complete frozen verification.
Run the Linux commands above, then run:

```bash
python3.11 scripts/materialize_quality_repair.py
bash .vendor/quality_repair/verify_handoff.sh
python3.11 scripts/verify_vendor_sources.py
```

The optional original-archive check is local and offline:

```powershell
.\.venv\Scripts\python.exe scripts\verify_vendor_sources.py --quality-archive C:\Users\Admin\Desktop\quality_repair_source_handoff_20260710.tar.gz
```

## Known platform differences

`.vendor/quality_repair/verify_handoff.sh` is POSIX-only because it uses Bash,
`find`, `xargs`, and `awk`. An inability to run that shell wrapper in native
PowerShell is not a quality-repair behavior failure. Windows runs the same
pytest payload directly. POSIX permissions, symlinks, and executable-file
semantics remain authoritative on Ubuntu when a test depends on them.

## Frozen vendor exception

Files materialized below `.vendor/quality_repair` and files copied below
`vendor/logic_self_audit_baseline` are frozen historical sources. They may
exceed the platform's 300-line file or 60-line function limits and must not be
refactored in a provenance-only change. New platform-owned scripts and tests
remain subject to those limits.
