# Term saturation and length normalisation

The two parameters in BM25 are not tuning knobs to be optimised blindly. Each has
a meaning, and knowing it is the difference between adjusting them from evidence
and adjusting them until a number looks better.

## Term saturation, k1

The term frequency factor is f(t,d) * (k1 + 1) / (f(t,d) + k1 * ...). As f(t,d)
grows, the numerator and the denominator grow together, so the factor approaches
an asymptote instead of growing without bound. That asymptote is the point: a
document containing a term ten times is more relevant than one containing it once,
but not ten times more relevant. The tenth occurrence carries almost no new
information.

k1 sets how quickly the curve flattens. At k1 equal to zero the formula degenerates
to pure binary presence and term frequency is ignored entirely. As k1 grows the
factor approaches linear in f(t,d). Values between 1.2 and 2.0 are the common
range; 1.2 is the default in this project.

## Length normalisation, b

Long documents contain more of every term by accident, simply because they are
long. The |d| / avgdl ratio corrects for that, scaled by b.

At b equal to zero there is no normalisation at all and long documents are
systematically favoured, because they have more chances to match. At b equal to one
normalisation is full. The usual value is 0.75, which accepts that a genuinely long
document probably does discuss more topics and should not be penalised completely.

b matters more than k1 in practice. A corpus of wildly uneven document lengths with
b set too low will be dominated by its longest documents, and the fix is a single
parameter rather than a rewrite.
