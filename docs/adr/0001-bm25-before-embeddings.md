# ADR-0001 — BM25 before embeddings

**Status:** accepted · **Date:** 2026-11-05

## Decision

Ship lexical BM25 retrieval first, implemented by hand. Add no embeddings, no vector store and no
reranker until BM25 has a measured baseline in a committed run artifact.

## Why

The comparison between lexical and semantic retrieval **is the result**. Shipping only an embedding
pipeline produces a system whose quality nobody can state — and whose failure mode ("it just returns
something vaguely related") cannot be described, because there is no baseline to describe it against.

There is also a defensibility argument. BM25 is roughly twenty lines of arithmetic that can be
explained on a whiteboard and checked by hand. A vector store is a dependency that either works or
doesn't, and the failure analysis stops at the library boundary. We start where we can explain every
number, then measure whether the expensive thing is worth it.

## Consequences

- Recall is expected to be **worse** than a semantic system on paraphrased questions. That is fine and
  will be reported honestly — it is the motivation for the next iteration, not a defect to hide.
- The project has no ML dependency, so a fresh clone runs with no install step.
- Phase 2 (embeddings) gets a real target to beat, and the README gets a genuine "we tried the simple
  thing first and here is what it bought us" section.
