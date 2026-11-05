# ADR-0005 — every published number comes from a committed artifact

**Status:** accepted · **Date:** 2026-11-05

## Decision

A metric may appear in the README only if a committed run artifact contains it. The artifact records
the dataset hash, the index hash, the code revision and the full configuration that produced it. No
hand-entered numbers. Ever.

## Why

An unverifiable metric is worse than no metric: it invites the reader to trust something they cannot
check, and when it is wrong it discredits the whole document. Evaluation numbers are also the easiest
thing in a portfolio to inflate accidentally — a number typed from a notebook cell that has since
changed configuration is a fabrication whether or not anyone intended it.

Recording inputs alongside outputs makes the number **reproducible**: re-run the command, get the same
number, or find out immediately that you can't.

## Consequences

- Reruns after any code, dataset or configuration change invalidate the old artifact; the README must
  point at the current one. Handling this is part of the definition of done, not an afterthought.
- Bad numbers get published. A measured `Recall@5 = 0.41` with an analysis of the failing cases is
  worth more than an unsourced `0.95`, and it is the one claim in a portfolio nobody can take apart.
- The report lists the **cases that scored zero**. The failures are the most interesting output of an
  evaluation and the most likely thing a reviewer will ask about.
