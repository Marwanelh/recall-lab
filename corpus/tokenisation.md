# Tokenisation

Tokenisation decides what counts as a word, and every later stage inherits that
decision. Indexing and querying must tokenise identically, or a term will be written
into the index under one form and looked up under another, and the retrieval failure
will appear as a scoring mystery.

The baseline used here: lowercase the text, split on any character that is not a
letter or a digit, and drop single-character tokens. Lowercasing makes matching
case-insensitive, which is almost always wanted. Splitting on punctuation separates
trailing commas and brackets from the words they touch. Dropping one-character tokens
removes noise at negligible cost.

## Stemming

Stemming reduces words to a common root so that "index", "indexing" and "indexed" all
match the same term. It improves recall on morphological variants and it makes the
system harder to reason about.

The specific cost is diagnosability. With stemming, a miss has two possible causes:
the term is genuinely absent, or the stemmer mapped it somewhere unexpected. Without
stemming there is one cause and it is checkable by searching the file.

## Stopwords

Removing common words such as "the" and "of" shrinks the index and speeds scoring,
because those terms carry little discriminating information and appear in nearly every
passage. The cost is that a query which is mostly stopwords loses most of its terms
and can return nonsense or nothing. Phrases and titles are full of such queries.

Both choices are legitimate. The point is that they are choices with costs, they
change the meaning of a metric, and they belong in a written decision rather than in
an unexamined line of code.
