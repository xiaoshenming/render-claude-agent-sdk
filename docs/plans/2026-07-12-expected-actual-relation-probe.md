# Expected/Actual Relation Probe Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether explicit mathematical relations extracted from the existing problem/solution input can be compared with relations in generated Manim code to detect geometry logic errors with low false positives.

**Architecture:** A bounded Claude Agent SDK Reviewer converts only explicit input claims into a strict relation contract. A local AST index extracts symbolic point and line facts from `candidate.py`; a deterministic comparator resolves semantic segment names, evaluates supported predicates, and reports contradiction, satisfied, or unknown. Evaluation pairs each mutated candidate with its original renderable source and never exposes mutation truth to the model or production modules.

**Tech Stack:** Python, `ast`, immutable dataclasses, Claude Agent SDK, pytest, Ruff.

---

## Boundaries

- Support only `line_endpoints`, `point_on_line`, `parallel`, `perpendicular`, `collinear`, `equal_length`, and `midpoint`.
- Every expected claim must include a verbatim source quote and source kind.
- The extractor receives problem/solution text only, never candidate code or mutation metadata.
- The comparator receives the extracted contract and candidate code only.
- `unknown` is reported, never converted to pass or contradiction.
- No sample IDs, titles, coordinates, expected fixes, or mutation types in production behavior.
- First evaluation measures detection only; it does not invoke a repair Agent.

## Task 1: Expected Relation Contract

1. Write failing parser tests for valid claims, unsupported relations, malformed operands, missing evidence, duplicate IDs, and forbidden repair hints.
2. Implement immutable contract models and a strict output schema.
3. Add a compact extractor prompt that requires explicit evidence and allows an empty claim list.

## Task 2: Symbolic Candidate Index

1. Write failing tests for point assignments, `Dot`, line endpoint references, semantic line aliases, and virtual segments formed by named points.
2. Preserve symbolic endpoint references even when numeric coordinates are unavailable.
3. Return unknown for dynamic or ambiguous values.

## Task 3: Deterministic Comparison

1. Write failing tests for satisfied, contradicted, and unknown relations.
2. Resolve `AD`, `line_AD`, and point-pair virtual segments without guessing from arbitrary names.
3. Bind every result to expected evidence and candidate source lines.

## Task 4: SDK Extractor And Frozen Probe

1. Add a no-edit Reviewer request that reads only `problem_text.txt` and emits the expected relation schema.
2. Record model, prompt/schema versions, token usage, elapsed time, and structured output.
3. Select diverse structural geometry mutations plus their untouched originals from `geo30_mutation_v5`.
4. Run extraction once per unique source problem, then compare both mutated and original code locally.

## Acceptance

- Zero wrong deterministic known facts in unit tests.
- Every attempted case appears in the report, including unsupported cases.
- Report mutation recall, original-code false-positive rate, unknown rate, average claims, Agent tokens, Agent rounds, and elapsed time.
- No production promotion unless the probe shows useful recall with no more than 10% false positives on untouched originals.
