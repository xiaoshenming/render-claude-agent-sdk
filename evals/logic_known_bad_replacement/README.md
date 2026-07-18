# Logic Known-Bad Replacement

This directory binds one unused mutation from an earlier frozen source pack. It
replaces the known-bad case used during Task 6 smoke debugging, so the Task 6
evaluation remains 30 bad cases without reusing that mutation.

The replacement is selected by data in `logic_known_bad/selection.json`; no
sample-specific branch exists in the Reviewer or evaluation runtime.

The replacement is independent at the mutation level, not at the source-code
level: the available renderable mutation packs reuse a small set of production
sources. A source-independent production holdout is required before launch.
