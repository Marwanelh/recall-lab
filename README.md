# recall-lab

![tests](https://github.com/Marwanelh/recall-lab/actions/workflows/tests.yml/badge.svg)

Point it at a folder of your own documents, ask questions, get passages cited back to the exact
file and character offsets — **and see how good the retrieval actually is, as numbers you can
reproduce.**

Anyone can wire an LLM to a vector store. The part almost nobody ships is knowing whether it works.

```bash
python -m recall_lab index corpus --out index.json
python -m recall_lab query index.json "what does k1 control" -k 3
python -m recall_lab evaluate index.json evals/dataset.jsonl --report evals/REPORT.md
```

No install step. No dependency. Python 3.10+ and the standard library.

---

## Measured results

38 questions · 33 indexed passages · 11 documents · chunk 800/150 · k1=1.2 b=0.75

| metric | value |
|---|---|
| Recall@1 | **0.724** |
| Recall@5 | **0.974** |
| Recall@10 | **1.000** |
| MRR | **0.873** |

Produced by `runs/run.json`, which records the dataset hash, the index hash, the code revision and
the full configuration. Regenerate with the `evaluate` command above; the numbers above come from
that artifact and nowhere else.

Every relevant passage is found within the top 10. The interesting number is the gap between
Recall@1 and Recall@5: the retriever almost always finds the right passage, and often does not put it
first. That is a **ranking** problem, not a retrieval problem, and the failure analysis below says
exactly where it comes from.

---

## What it does

| Module | Responsibility |
|---|---|
| **Ingest** | Walk a folder of `.md`/`.txt`, chunk on paragraph boundaries with overlap |
| **Index** | BM25, written by hand, saved as readable JSON |
| **Query** | Top-k passages, each carrying a citation handle; `--trace` records why |
| **Evaluate** | Committed dataset → Recall@K, MRR, and a committed run artifact |

### A citation is a file path and two integers

```
corpus/bm25-scoring.md#0-760
```

Not `chunk_00417`. You can open the file and count to the offset. That is the difference between a
citation a reviewer can check and one they have to take on trust, and the invariant
`original[start:end] == chunk.text` is asserted in the test suite.

### The index is JSON you can read

Open `index.json` and the posting lists are right there, so the score arithmetic can be verified by
hand against the specification. It is larger and slower than a binary format — a trade made on
purpose, and stated rather than hidden ([ADR-0002](docs/adr/0002-json-index.md)).

### `--trace` records what it rejected

```
$ python -m recall_lab query index.json "what does the k1 parameter control" -k 3 --trace
 1. 6.796  corpus/term-saturation-and-length-normalisation.md#994-1671
 2. 4.257  corpus/mean-reciprocal-rank.md#0-685
 3. 3.241  corpus/term-saturation-and-length-normalisation.md#540-1144

trace: 6 tokens (6 unique), 20 passages scored above zero, 3 returned
       not found in the corpus: control
       timings: tokenize 0.01ms · score 0.07ms · rank 0.01ms
```

`not found in the corpus: control` is the kind of statement most retrieval systems cannot make. It
distinguishes "the passage is absent" from "the passage was found but ranked too low", and those two
have completely different fixes.

---

## Where it fails

Nine of thirty-eight cases did not put the best passage first. Reading them, they fall into three
groups — each with a name and a cause, because a failure count on its own is not an analysis.

### 1. The file's own title chunk wins (4 cases)

The opening chunk of a document repeats the topic words densely and is short, and BM25 rewards both
high term frequency and short documents. So for *"what does mrr ignore"* the intro paragraph of
`mean-reciprocal-rank.md` outranks the paragraph that actually answers it.

This is BM25 behaving exactly as specified. The fix is a deliberate choice — down-weight the first
chunk, or add the document title as a field rather than as text — and whichever is chosen has to be
measured against these same 38 cases.

### 2. Overlap makes a passage compete with its own predecessor (4 cases)

Chunks overlap by 150 characters, so the tail of one chunk is repeated at the head of the next. When
the answer sits just inside that overlap, both chunks contain it and the earlier, shorter one usually
scores higher.

The `relevant` set for these cases lists **both** handles, because both genuinely answer the
question. The cost is visible in Recall@1 and invisible in Recall@5 — which is what an overlap
setting is supposed to trade, and now there is a number attached to it.

### 3. No stemming causes a hard miss (1 case)

*"what does lexical retrieval match"* fails against a passage that reads *"Lexical retrieval
**matches** the words actually present in the text."*

`tokenize("match")` returns `['match']`; `tokenize("matches")` returns `['matches']`. The terms do not
match, so the passage scores zero on that term and the case is lost. This is the cost of
[ADR-0004](docs/adr/0004-no-stemming.md) — the decision to keep every score explainable term by term
— and it is now a measured cost rather than an assumption. A stemmer would fix this case; whether it
earns its place is decided by re-running these 38 cases with and without one.

---

## Design decisions

Six decisions, each with the tradeoff written down rather than implied:

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-bm25-before-embeddings.md) | BM25 before embeddings — the comparison is the result |
| [0002](docs/adr/0002-json-index.md) | The index is readable JSON, at a cost in size and speed |
| [0003](docs/adr/0003-citation-handles.md) | A citation is a path and character offsets, plus a content hash |
| [0004](docs/adr/0004-no-stemming.md) | No stemming, no stopwords — and here is what that costs |
| [0005](docs/adr/0005-numbers-from-artifacts.md) | No number is published without a committed artifact |
| [0006](docs/adr/0006-standard-library-only.md) | No third-party dependency, so a clone just runs |

The specification, including the exact chunking rules, the BM25 formula, the dataset format and the
metric definitions, is in [SPEC.md](SPEC.md).

---

## Limitations

- **Bag of words.** Word order is ignored, so a phrase query cannot be distinguished from its
  scrambled form.
- **The corpus is 11 short documents.** At this size BM25 is instant and the JSON index is trivial.
  Neither property survives a corpus a thousand times larger, where the whole-index-in-memory design
  becomes the limit.
- **The dataset is small.** 38 cases supports the direction of these results, not small differences
  between systems. Treat a two-point gap as unresolved.
- **Lexical only.** Paraphrase that shares no words is guaranteed to fail, and the analysis above
  shows vocabulary mismatch already losing a case.
- **No PDF ingestion.** Only `.md` and `.txt`.

---

## Tests

```bash
python -m unittest discover -s tests -t .
```

63 tests, no dependency. They pin the BM25 arithmetic to a value worked out by hand, assert the
citation invariant `original[start:end] == chunk.text` for every chunk, check that a saved and
reloaded index scores identically, and verify the two rules that make the evaluation trustworthy: a
case citing an unresolvable passage **fails the run** rather than scoring zero, and a case whose
passage has moved is **reported as stale** rather than counted as a miss.

---

## If you are reading this as a work sample

The retrieval is twenty lines of arithmetic. The parts worth your attention are the ones that make
claims checkable: citations that resolve to characters a human can verify, an index you can inspect,
traces that record rejected candidates, and an evaluation whose every number names the inputs that
produced it — including the numbers that are not flattering.
