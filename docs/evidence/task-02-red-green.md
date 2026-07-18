# Task 02 Red/Green Evidence

This page records the local test-first sequence used for the source provenance
verifier. It is process evidence from the working session, not a claim that a
dedicated RED commit exists in Git history. No separate commit was created or
reconstructed for the failing state.

## RED: Before Implementation

The provenance tests were run before `scripts/verify_vendor_sources.py` and
`docs/source-provenance.md` were implemented:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_source_provenance.py -q
```

Observed result: `5 failed`.

Failure reason categories, corresponding to the five tests:

1. Source metadata contract: the offline verifier and its baseline metadata
   were not implemented.
2. Documentation contract: `docs/source-provenance.md` did not exist.
3. Positive integrity path: the verifier CLI could not report a passing frozen
   source inventory.
4. Tamper rejection path: no verifier existed to report a hash mismatch.
5. Missing-file rejection path: no verifier existed to report a missing
   required file.

These are categories from the original failing run, not a newly synthesized
failure transcript.

## GREEN: After Implementation

After adding the provenance document, manifest-aware verifier, frozen source
metadata, and negative-path handling, the same command was run again:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_source_provenance.py -q
```

Observed result: `5 passed`.

The five tests cover required metadata, documentation authority and platform
exceptions, a valid frozen inventory, hash tampering rejection, and missing
required-file rejection.
