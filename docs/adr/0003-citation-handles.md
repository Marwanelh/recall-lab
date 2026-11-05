# ADR-0003 — a citation is a path plus character offsets

**Status:** accepted · **Date:** 2026-11-05

## Decision

Identify every chunk by `<relative-path>#<start>-<end>` (character offsets into the original file),
and carry a `content_sha256` alongside it.

## Why

The project's promise is that an answer can be **checked**. A citation that is a synthetic id
(`chunk_00417`) can only be checked by trusting the index. A path and two integers can be checked by
opening the file. That difference is the whole credibility of the tool, and it also means a human can
verify a retrieval failure without running any code.

Offsets into the **original** text, not a normalised copy, keep the handle honest: the invariant
`original[start:end] == chunk.text` is asserted in the test suite.

## Consequences

- Handles move when earlier text in a file is edited, so a handle is **not** a permanent identifier.
- The `content_sha256` resolves this: a dataset case whose handle exists but whose hash has changed is
  reported as **stale** — not scored as a miss, not silently dropped. A stale dataset is a fact the
  report must state, because scoring it would produce a number that looks valid and isn't.
- Dataset cases therefore depend on the corpus being committed and stable. Intended: the corpus is
  versioned with the dataset it is scored against.
