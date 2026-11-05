# Chunking

Retrieval does not return documents; it returns passages. If passages are cut badly,
no scoring function can recover the relevance that the cut destroyed.

## Why chunk at all

A whole document is usually too much context and too diffuse a signal. A document
about six topics will match almost any query weakly, and the matched text will be
buried in material that has nothing to do with the question. Splitting into passages
makes each unit about fewer things, so the match is sharper and the reader gets
sent to the relevant part rather than to the top of a long file.

## Fixed size against paragraph boundaries

Cutting every N characters produces uniform chunks and is trivial to implement, but
it slices mid-sentence and can separate a heading from the text it introduces.

Cutting on paragraph boundaries respects the author's own structure. The cost is
varying chunk sizes, which is exactly what BM25's length normalisation exists to
handle. This project accumulates paragraphs until a character target is reached and
only hard-splits a single paragraph when it is larger than the target on its own.

## Overlap

If a fact spans a boundary, a chunk that ends mid-fact answers nothing and a chunk
that begins mid-fact is confusing. Overlap repeats the tail of one chunk at the
start of the next, so the fact appears whole in at least one of them.

The cost is duplicated text: the index grows, and a query can return the same
passage twice under two handles. Overlap is worth it when questions span boundaries
often, and wasted when the documents are already written in short independent
sections.

## The measurement that matters

Chunk size and overlap are hyperparameters, and the honest way to choose them is to
build the index twice and run the same evaluation against both. The difference in
recall is the answer. Anything else is a preference dressed up as a decision.
