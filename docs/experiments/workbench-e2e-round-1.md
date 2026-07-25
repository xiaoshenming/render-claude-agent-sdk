# Workbench E2E Round 1

## Frozen Result

- Jobs: 15
- Delivered: 10, including 2 layout-warning releases
- Held: 5
- Total tokens: 706,310
- Average tokens: 47,087

## Failure Attribution

- Three baseline render failures came from generated source: overlapping Pango
  style keys or invalid LaTeX.
- One generation request failed on an HTTP 502 without a retry.
- One non-blocking Reviewer `record_only` decision was incorrectly routed to hold.
- Two overlap repairs reached zero blocking and passed vendor compile, recheck, and
  diff audit, but the platform's stricter semantic fingerprint rejected them.

## Round 2 Hypothesis

Apply four sample-independent changes only:

1. Retry transient or incomplete generation once and preserve attempt evidence.
2. Add generic Pango-style and LaTeX validity constraints to every generation prompt.
3. Treat Reviewer `record_only` as releasable evidence while retaining `human_review`
   as a hold.
4. When vendor evidence is clean but the platform semantic guard is conservative,
   require external render recheck and release with a recorded warning.

No task ID, object name, formula, or case-specific coordinate is used by these changes.
