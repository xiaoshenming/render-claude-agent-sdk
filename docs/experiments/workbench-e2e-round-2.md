# Workbench E2E Round 2

## Frozen Result

- Jobs: 15
- Delivered: 12, including 4 warning releases
- Held: 3
- Total tokens: 792,361
- Average tokens: 52,824

## Change Effect

- Delivery rate improved from 66.7% to 80.0%.
- One transient generation failure recovered on the second request.
- Two vendor-clean overlap candidates were externally re-rendered and released with
  the conservative platform semantic warning retained.
- Two layout calls exceeded the 60k repair budget; their original renderable videos
  were retained with warnings rather than starting another Agent round.

## Residual Failures

- Two generated candidates still failed baseline render: one used Chinese inside Tex,
  and one emitted overlapping Pango style keys despite the first generic warning.
- One Logic Reviewer call failed closed on a provider `server_error`.

## Round 3 Hypothesis

Keep all Agent policies and budgets unchanged. Add one non-Agent, full-regeneration
recovery after a baseline render failure, passing only the bounded render error tail.
Strengthen the universal prompt rule for Chinese Tex and duplicate Pango style matches.
