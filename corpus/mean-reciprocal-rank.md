# Mean reciprocal rank

Mean reciprocal rank, abbreviated MRR, measures where the first relevant result
appears in the ranking. For each query you take the reciprocal of the rank of the
first relevant passage: 1 if it is first, one half if it is second, one third if it
is third. Queries that find nothing contribute zero. MRR is the mean of those values
across all queries.

## What it captures that recall does not

Recall@K does not care about order within the top K. A relevant passage at rank one
and the same passage at rank ten score identically at K=10. MRR does care, and it
answers a different question: when the system does find the right thing, does it put
it near the top?

That matters whenever a human or a model reads only the first result. If the right
passage is reliably found but usually sits at rank seven, recall looks respectable
and the product is still bad.

## The limitation to state out loud

MRR ignores every relevant passage after the first. A query with five relevant
passages where one is found at rank two scores the same as a query with a single
relevant passage found at rank two. It is a single-number summary, and like every
single-number summary it hides structure.

Report MRR next to Recall@K rather than instead of it. MRR tells you about ranking
quality among the successes; recall tells you how often there is a success at all.
A run where recall is high and MRR is low is a reordering problem, which is a much
cheaper fix than a retrieval problem.
