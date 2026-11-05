# ADR-0004 — no stemming and no stopword list

**Status:** accepted · **Date:** 2026-11-05

## Decision

Tokenise by lowercasing and splitting on `[^a-z0-9]`, dropping tokens of one character. Do not stem,
do not remove stopwords.

## Why

Both are easy wins on paper and both make the system harder to reason about:

- **Stemming** merges `index`/`indexing`/`indices` inconsistently, so a miss becomes untraceable —
  you cannot tell whether the query term was absent from the corpus or merely mangled by the stemmer.
  With no stemming, "the term is not in the corpus" is a statement you can verify by searching the file.
- **Stopword removal** silently deletes query terms. If a question is about "to be or not to be", the
  scores stop corresponding to anything a reader can see.

Neither is forbidden, and either may be measured later. The claim here is narrower: **the baseline must
be a system whose scores are explainable term by term.** Optimisations get added against a baseline and
measured — not assumed at the start.

## Consequences

- Vocabulary is larger and average postings are longer than a stemmed index; the index is bigger.
- Recall on morphological variants (`train` vs `training`) will be worse than a stemmed system. If the
  failure analysis shows that is a dominant error mode, stemming becomes a measured change with a
  before/after number attached — which is the point.
- Tokenisation is fully specified in the SPEC, so the token stream is reproducible and testable.
