# Inverted indexes

An inverted index maps each term to the list of documents that contain it. That
inversion is what makes search fast: instead of reading every document to see
whether it mentions a term, you look the term up and get the documents directly.

The structure is a dictionary from term to a posting list. Each posting records
which document the term occurs in, and usually how many times, because BM25 needs
the term frequency. Postings are normally kept in document order so that two posting
lists can be intersected efficiently when a query has several terms.

## Why the dictionary is the expensive part

The posting lists are large but predictable. The dictionary is the part that decides
how the index is stored: a real search engine keeps a sorted term dictionary with a
prefix-compressed structure so that a term lookup is a binary search over compressed
blocks. This project uses a plain dictionary because the corpus fits in memory, and
the tradeoff is stated rather than hidden.

## Segmented indexes

Production engines such as Lucene do not rewrite one giant index on every update.
They write a new immutable segment and search all segments together, merging them in
the background. Immutability makes concurrent reads safe without locking, and
merging keeps the number of segments bounded.

Building one flat index is enough at this scale. The reason segments exist is worth
knowing, because it explains why a search engine can accept writes continuously while
this design must rebuild from scratch.
