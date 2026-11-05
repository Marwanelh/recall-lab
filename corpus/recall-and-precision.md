# Recall, precision, and which one to report

Recall asks what fraction of the relevant passages were found. Precision asks what
fraction of the returned passages were relevant. They trade against each other, and
which one matters depends entirely on what happens next.

For a retrieval step that feeds a language model, recall is usually the constraint
that binds. If the passage containing the answer is not in the retrieved set, no
amount of good generation will produce a correct answer grounded in a source. Extra
passages cost tokens and can distract, but a missing passage makes the task
impossible. That is why this project reports Recall@K and MRR and treats precision as
a secondary signal.

## Recall@K

Recall@K is the fraction of the relevant passages that appear in the top K results.
It is reported at several K because the answer to "is it good" depends on how much
context the next stage can afford. Recall@1 measures whether the single best passage
is right, which matters when only one passage will be shown. Recall@10 tolerates a
noisier ranking that a later stage will filter.

Reporting a single K hides this. A system can look strong at K=10 and be useless at
K=1, and only the table of several cut-offs reveals it.

## Why not precision alone

A retriever that returns every passage in the corpus has perfect recall and useless
precision. A retriever that returns one passage has perfect precision when it is
right and zero recall when the corpus needs two sources to answer. Neither number is
meaningful by itself, which is why evaluation should always report at least one
recall-oriented metric and the failure cases that produced it.
