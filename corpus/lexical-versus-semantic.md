# Lexical against semantic retrieval

Lexical retrieval matches the words actually present in the text. Semantic retrieval
matches meaning, by comparing learned vector representations of the query and the
passages. They fail in different places, and knowing which failure you have is worth
more than picking a side.

## Where lexical wins

Exact identifiers. A model number, an error code, a product SKU, a function name, a
person's surname. Semantic models routinely miss these because a rare token has almost
no representation to generalise from, while BM25 scores them highly precisely because
they are rare. Technical documentation, code, and support tickets are full of such
tokens.

Lexical retrieval is also explainable by construction: a result can be justified term
by term, and a miss can be shown to be an absent term rather than a lost meaning.

## Where semantic wins

Paraphrase and vocabulary mismatch. A question about "make the site faster" and a
passage about "reducing page load latency" share no tokens and are trivially related
by meaning. BM25 scores that pair at zero and cannot be tuned into finding it.

## Why measure before combining

Hybrid retrieval that merges both rankings is the usual answer and is often genuinely
better. It is also more code, more dependencies, and a second thing that can fail. The
only defensible reason to add it is a measured baseline showing which errors lexical
retrieval makes, and evidence that the semantic component fixes that class of error
rather than merely adding a different set of misses.

Build the lexical baseline first. Its failures name the problem the next component
has to solve.
