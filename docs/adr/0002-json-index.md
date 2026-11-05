# ADR-0002 — the index is a readable JSON file

**Status:** accepted · **Date:** 2026-11-05

## Decision

Serialise the index as plain JSON: parameters, chunk metadata, posting lists. Not a pickle, not a
binary format, not a database.

## Why

The index is the artefact a reviewer needs to trust, and trust comes from being able to look. With
JSON a stranger can open the file, find a term's posting list, and verify the IDF and the score
arithmetic by hand against the SPEC. With a pickle they can only take our word for it.

JSON is also diffable. When chunking changes, the index diff shows exactly which chunks appeared,
moved or vanished — which is how a recall change gets explained rather than guessed at.

## Consequences

- Larger on disk and slower to build than a compact binary encoding.
- Whole index is held in memory; corpus size is bounded by RAM. Acceptable at the documented scale
  (a personal document set), and stated as a limitation in the README rather than discovered by a user.
- Float round-tripping is explicit: we serialise with `repr`-safe JSON floats and recompute `avgdl`
  from stored lengths on load, so a loaded index scores identically to a freshly built one. This is
  asserted in a test — a saved-then-loaded index must return identical results.
