# Building an evaluation dataset honestly

The dataset is the most important artefact in a retrieval evaluation and the easiest
one to get quietly wrong. A dataset that flatters the system produces a number that
looks impressive and cannot survive a question.

## Choose the relevant passage by topic, not by retrieval output

The tempting shortcut is to run the retriever, take its top result, and record that
as the relevant passage. The resulting metric measures agreement with itself and will
be near perfect. It is circular, and it is the most common way an evaluation number
becomes meaningless.

Decide what is relevant by reading the corpus. The judgement must be independent of
the system being measured, or the measurement is worthless.

## Never score a broken case as a miss

If a dataset case cites a passage that the index cannot resolve, the dataset and the
corpus have diverged. Scoring that case zero silently converts a broken input into a
worse metric, and the number that comes out looks valid.

The correct behaviour is to fail the run. A dataset error and a retrieval failure are
different things and must not be averaged together.

## Detect staleness, do not hide it

If the corpus is edited, character offsets move and a handle that once pointed at the
right passage may now point at different text. A case like that is stale. It should be
reported and excluded, never scored as a miss, because the miss would be an artefact
of editing rather than a property of retrieval.

## How many cases

Twenty-five is a floor for publishing a number, and even then it is underpowered. A
difference of a few points between two systems on twenty-five cases is noise. Report
the case count with every metric, and treat small differences as unresolved rather
than as improvements.
