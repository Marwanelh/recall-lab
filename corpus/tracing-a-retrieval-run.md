# Tracing a retrieval run

A retrieval system that returns an answer without recording how it got there is not
debuggable. When a query returns the wrong passage, the useful question is not "what
did it return" but "what did it consider, what did it score them, and what did it
discard".

## What a trace should record

The tokenised query, so that a surprising result can be traced to tokenisation rather
than to scoring. For each term, how many passages matched it, because a term matching
zero passages explains an empty result immediately and a term matching every passage
explains a useless one. The scored candidates before truncation to k, because the
passage that was wanted is very often at rank six when five were returned. And
timings, because a ranking that is correct but slow is a different problem from one
that is fast and wrong.

## Why the discarded candidates matter

Reporting only the top k hides the near misses. A system returning five results where
the relevant passage is at rank six looks broken; the same system returning ten
results looks fine. Without the pre-truncation ranking you cannot tell the difference
between "the passage was not found" and "the passage was found but cut off", and
those have completely different fixes.

## The cost

Recording a trace means keeping intermediate state that is otherwise thrown away. In
a high-throughput system that is real overhead. The tradeoff to make deliberately: log
traces always in development and on a sampled fraction in production, rather than
never or always.
