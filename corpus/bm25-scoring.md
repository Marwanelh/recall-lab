# BM25 scoring

BM25 ranks a document for a query by summing, over the query's terms, a weight per
term that grows with how often the term appears in the document and with how rare
the term is across the collection. The two forces it balances are term frequency
saturation and document length normalisation.

The score for a document d and query terms q is the sum over each term t in q of:

    IDF(t) * ( f(t,d) * (k1 + 1) ) / ( f(t,d) + k1 * (1 - b + b * |d| / avgdl) )

f(t,d) is how many times t occurs in d, |d| is the length of d in tokens, avgdl is
the mean document length in the collection, and k1 and b are the two parameters.

The inverse document frequency term is usually the smoothed form:

    IDF(t) = ln( 1 + (N - n(t) + 0.5) / (n(t) + 0.5) )

where N is the number of documents and n(t) is the number of documents containing
t. The additive 1 inside the logarithm keeps the value non-negative even when a
term appears in more than half the collection, which the unsmoothed classic form
does not.

BM25 is a bag-of-words model. It ignores word order entirely, which is why it
cannot tell "dog bites man" from "man bites dog". That is a real limitation and
the reason phrase queries need support beyond the scoring function.
