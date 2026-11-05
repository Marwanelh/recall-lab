# ADR-0006 — standard library only

**Status:** accepted · **Date:** 2026-11-05

## Decision

The core has no third-party runtime dependency. Python standard library, and `unittest` for tests.

## Why

A reviewer must be able to clone the repo and run it **without resolving a dependency tree**. Every
dependency is a reason to stop reading, and an install step is where a curious recruiter decides it is
not worth their time.

It also keeps the interesting code visible. Reaching for a BM25 library or a search framework would
delete the exact thing the project exists to demonstrate — the scoring model. `math.log` and `dict`
are enough.

## Consequences

- No `pip install`. `python -m recall_lab ...` works on a clean Python 3.10+.
- We implement tokenisation, the inverted index and JSON (de)serialisation ourselves — all bounded,
  explainable work, and all covered by tests.
- Some things are genuinely harder without libraries (fast numeric work, PDF parsing). Those are cut
  from scope rather than pulled in as dependencies; see the SPEC's out-of-scope list.
- CI is fast, and there is no supply-chain surface to audit.
