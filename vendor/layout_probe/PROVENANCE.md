# Layout Probe Provenance

- Source snapshot:
  `DEV-PB5/apps/render/app/workers/validation/layout/probe_runner.py`
- Extracted symbol: `PROBE_RUNNER_SOURCE`
- Materialized file: `probe_runner.txt`
- SHA-256 (materialized `probe_runner.txt`, authoritative):
  `518588a68b44c7d09f6164fe226bb5a6cbc343bad7664285517d819077275d92`
- Note: the hash recorded at packaging time
  (`226e34e3048abd470ca298cb898e2e6e4d7f779d1bf7227d6f804453e11b6724`)
  never matched the materialized file in this repository's history and does
  not match any known DEV-PB5 source revision; it is retained only as a
  packaging-record artifact. The runner's structure is now behaviorally
  pinned by `tests/unit/operator/test_geometry_sidecar_runner.py`
  (AST contract: `main` / `_collect_objects` present, no top-level manim
  import), and every run's `runtime_manifest.json` records the live
  detector/probe hashes.
- Purpose: deterministic, multi-snapshot Manim object and BBox collection.

The runtime executes this materialized resource as a standalone Python program.
It does not import DEV-PB5 at runtime.
