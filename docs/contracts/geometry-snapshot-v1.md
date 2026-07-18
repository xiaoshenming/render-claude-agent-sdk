# Geometry Snapshot v1

`manim-quality.geometry-snapshot.v1` is the renderer-to-quality-platform
contract for observed geometry. It carries measurements, identity, and source
provenance only. It must not contain diagnoses, expected values, repair hints,
severity, or delivery decisions.

## Capture boundary

The render worker owns object registration and checkpoint timing. It supplies:

- the SHA-256 hash of the exact candidate code;
- the Scene identifier;
- a stable checkpoint identifier such as `play-7` or `final-visible`;
- one stable logical object ID per observed object;
- the source Scene, line range, and a bounded source excerpt;
- the renderer object through the duck-typed capture adapter.

The adapter reads only these public observations:

| Kind | Required observation | Snapshot state |
| --- | --- | --- |
| `point` | `get_center()` | `position` |
| `line` | `get_start()`, `get_end()` | `start`, `end` |
| `circle` | `get_center()`, `radius` | `center`, `radius` |
| `polygon` | `get_vertices()` | `vertices` |

The adapter does not import Manim. A render worker may therefore integrate it
without making the quality platform depend on a particular Manim release.

## Checkpoint semantics

- `runtime_checkpoint` means the state observed after a named render action.
- `runtime_final` means the final visible state selected by the render worker.
- `static_initial_state` is reserved for AST-only fallback evidence and must not
  be represented as rendered final geometry.

The caller must choose checkpoints that correspond to visible lesson states.
The quality platform does not infer animation timing from source code.

## Fail-closed behavior

Missing accessors, invalid dimensions, non-finite coordinates, dynamic values,
and unsupported objects produce `status: unknown` with a reason code. They are
not approximated. Duplicate logical IDs, cross-Scene source bindings, invalid
hashes, or malformed contract fields reject the complete snapshot.

An `unknown` observation cannot justify PASS or automatic repair. After any
repair, the render worker must capture a new snapshot with the new code hash;
facts from the old snapshot are stale and cannot certify the edited code.

## Minimal example

```json
{
  "schema_version": "manim-quality.geometry-snapshot.v1",
  "code_hash": "sha256:<64 lowercase hexadecimal characters>",
  "scene_id": "Solution",
  "checkpoint_id": "play-7",
  "provenance": "runtime_checkpoint",
  "objects": [
    {
      "object_id": "altitude",
      "kind": "line",
      "status": "known",
      "reason_code": null,
      "state": {
        "start": [0, 2, 0],
        "end": [0, 0, 0]
      },
      "source": {
        "scene_id": "Solution",
        "line_start": 42,
        "line_end": 42,
        "excerpt": "altitude = Line(A, foot)"
      }
    }
  ]
}
```
