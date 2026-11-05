# Why the index is a readable file

Storing a search index as a plain readable file rather than a compact binary is a
deliberate trade, and the trade is worth naming.

## What it buys

A reviewer can open the index and check it. The parameters are at the top, the posting
lists are visible, and the arithmetic in the scoring formula can be verified by hand
against the stored counts. That matters enormously when the index is the artefact a
reader has to trust: a number produced by an opaque file can only be believed, while a
number produced by a readable one can be checked.

It also diffs. When the chunking changes, the index diff shows exactly which passages
appeared, moved or disappeared, which is how a change in recall gets explained instead
of guessed at. A binary format would show a changed file and nothing more.

## What it costs

Size and speed. JSON is larger than a compact binary encoding and slower to parse, and
holding the whole structure in memory bounds the corpus by available RAM. The
alternative for a large corpus is a real index format, and adopting one would import a
dependency and hide the arithmetic this project exists to show.

## The honest framing

This is the right trade at the documented scale, for a tool whose purpose is
explainability. It is the wrong trade for a search engine serving millions of
documents, and saying so is part of the decision rather than a weakness in it.
