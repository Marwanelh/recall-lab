# recall-lab — specification

Point it at a folder of your own documents, ask questions, get passages cited back to the exact
file and character offsets — and see **how good the retrieval actually is, as numbers you can
reproduce.**

The second half is the product. Wiring an LLM to a vector store is a tutorial. Saying *"Recall@5 is
0.71 on a 40-case dataset, here is the run artifact, and here is where it fails"* is engineering.

This file is the contract. No implementation file exists until the rules here are settled
(M2 gate). Every rule below is written to be checkable by a stranger.

---

## 0. Scope

Four modules, standard library only, no network at query time.

| # | Module | Responsibility |
|---|---|---|
| 1 | **Ingest** | Walk a folder, read `.md` / `.txt`, chunk deterministically |
| 2 | **Index** | BM25, built by hand, serialised to readable JSON |
| 3 | **Query** | Top-k passages, each with a citation handle and a trace |
| 4 | **Evaluate** | Committed dataset → Recall@K, MRR, a committed run artifact |

Out of scope until BM25 is measured: embeddings, vector stores, reranking, OCR, PDF, any LLM.
See ADR-0001.

---

## 1. Ingest — chunking rules

Input: a directory. Read files matching `**/*.md` and `**/*.txt`. Skip dotfiles, `node_modules`,
`.git`. Sort the file list by relative POSIX path so ingestion order is reproducible.

**Chunk boundaries** (the whole point — chunking decides recall):

1. Split the file into paragraphs on runs of two or more newlines.
2. Accumulate paragraphs into a chunk until adding the next would exceed `CHUNK_TARGET_CHARS`.
3. If a **single** paragraph exceeds the target, hard-split it: cut at the last whitespace before the
   limit; if there is no whitespace, cut at the limit.
4. Emit the chunk, then begin the next chunk with the trailing `CHUNK_OVERLAP_CHARS` characters of the
   one just emitted, so context spanning a boundary survives.

```
CHUNK_TARGET_CHARS  = 800
CHUNK_OVERLAP_CHARS = 150
```

Both are module constants, overridable by CLI flag, and **recorded in every run artifact** — a
recall number is meaningless without the chunking that produced it.

**Offsets are character offsets into the original file**, not into the normalised text. They must
satisfy: `original[chunk.start:chunk.end] == chunk.text`. This is asserted in tests and is what makes
citations verifiable.

A chunk is dropped if it has no alphanumeric character.

---

## 2. Citation handles

Every chunk has a handle:

```
<relative-path>#<start>-<end>          e.g.  notes/bm25.md#120-940
```

The handle is the citation. It is:

- **human-verifiable** — you can open the file and count to the offset;
- **stable under edits elsewhere in the file** — offsets move only when the text before them moves;
- **the join key** between the dataset, the index, the query results and the eval report.

Every chunk also carries `content_sha256` (of its exact text). Handles are position-based and can
therefore collide across edits; the hash is what detects that. A dataset case referencing a handle
whose hash has changed is reported as **stale**, not silently scored. See ADR-0003.

---

## 3. Index — BM25

Tokenisation: lowercase, split on any character that is not `[a-z0-9]`, drop tokens shorter than 2.
Numbers are kept. **No stemming, no stopword list** — see ADR-0004.

One document = one chunk. Standard BM25 with:

```
k1 = 1.2
b  = 0.75
```

```
score(q, d) = Σ_t  IDF(t) · ( f(t,d)·(k1+1) ) / ( f(t,d) + k1·(1 − b + b·|d|/avgdl) )
IDF(t)      = ln( 1 + (N − n(t) + 0.5) / (n(t) + 0.5) )
```

`k1` and `b` are recorded in the run artifact. Scores are floats; ranking ties break on
`citation handle` ascending, so a given index and query always produce the same order.

**The index is JSON.** Not a binary blob, not a pickle, not a database. It stores `k1`, `b`, the
chunk list (handle, hash, path, offsets, length, token count, **text**) and the posting lists. It is
inspectable, diffable, and a reviewer can check the arithmetic by hand. See ADR-0002. The cost is
memory and build time; that cost is acceptable and is stated in the README.

Storing the chunk text makes the index self-contained: `query` and `evaluate` take only the index
file, with no need to re-read the corpus, so a run cannot silently use different text from the one
that was indexed. It also means the index is a full copy of the corpus — the trade-off that makes the
whole-in-memory design the next limit as the corpus grows.

The index records `index_sha256` — a hash over the serialised index — which the run artifact cites.

---

## 4. Query

```
query(text, k) -> [ {handle, score, path, start, end, snippet, sha256} ]
```

- Same tokenisation as indexing.
- Score every chunk; return the top `k` with `score > 0`.
- Zero-score chunks are not results. An empty result set is a valid, reportable outcome.

**`--trace`** writes, for the query: the tokenised terms, how many chunks each term matched, the
top-20 before truncation with scores, the final `k` chosen, and wall-clock timings.

This exists because "the retrieval returned something" is not a debuggable statement. The trace is
the answer to *"why did it return that, and what did it consider and reject?"* — the record that is
missing from most retrieval systems, and the thing a reviewer can actually audit.

---

## 5. Dataset

JSONL, one case per line, committed to the repo:

```json
{"id": "bm25-saturation", "question": "how does term saturation work", "relevant": ["notes/bm25.md#120-940"]}
```

- `id` unique, non-empty.
- `question` non-empty.
- `relevant` — one or more citation handles.
- **No relevant handle may be empty or absent from the index.** A case referencing a handle that is
  not in the index makes the run **fail**, not score zero. Silent zeroes have caused more wrong
  conclusions than any other evaluation bug.

A hand-built dataset is fine and expected. What matters is that it is committed, hashed, and scored
the same way every time. Minimum for a published number: **25 cases**. Below that, report the
number but label it underpowered.

---

## 6. Metrics

For each case, ranked results `r_1..r_k` and the relevant set `R`:

```
Recall@K = |{relevant handles in r_1..r_K}| / |R|
MRR      = 1 / (rank of the first result in R), or 0 if none is in the top K
```

Report `Recall@1`, `Recall@5`, `Recall@10` and `MRR`, as the mean over cases. Also reported:

- per-case results (so any aggregate can be recomputed and any outlier found);
- the cases scoring zero, listed by id — **the failures are the interesting output.**

No metric is reported without its dataset hash, index hash and code revision.

---

## 7. Run artifact — the anti-fabrication rule

`evaluate` writes a committed JSON artifact containing:

| Field | Why |
|---|---|
| `dataset_sha256`, `index_sha256` | which inputs produced this |
| `code_revision` | which code produced this |
| `k1`, `b`, `chunk_target_chars`, `chunk_overlap_chars` | which configuration produced this |
| `dataset_cases`, `index_chunks` | the sample size, in the artifact |
| per-case: id, rank of first hit, recall, whether the case was stale | traceability |
| aggregates | the headline numbers |
| `stale_cases` | handles whose content hash moved — reported, not scored away |

**A number may only appear in the README if a committed artifact contains it.** No hand-entered
results, ever. If the numbers are bad, publish the bad numbers and analyse them: a measured 0.41 with
an honest failure analysis is worth more than a claimed 0.95, and it is the one thing in a portfolio
nobody can take apart. See ADR-0005.

---

## 8. CLI

```
recall-lab index   <docs-dir>  --out <index.json>
recall-lab query   <index.json> "<question>" -k 5 [--trace]
recall-lab evaluate <index.json> <dataset.jsonl> --out <run.json> [--report <report.md>]
```

Exit codes: `0` success · `1` usage error · `2` validation failure (bad dataset, missing handle).

Every run prints its artifact path. Nothing is silent.

---

## 9. Definition of done

- [ ] A fresh clone runs `index` → `query` → `evaluate` with **no install step**.
- [ ] Every citation handle resolves: `original[start:end] == chunk text`, asserted in tests.
- [ ] The README's first table is produced by a committed run artifact, not typed.
- [ ] The README names the cases that fail and what they have in common.
- [ ] The dataset and index are committed; the numbers reproduce.
- [ ] No client data, no private documents, no credentials — the committed corpus is one we may publish.
