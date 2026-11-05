"""Query: rank chunks, return cited passages, and explain the ranking.

Every result carries the citation handle, so an answer built from it can point at
the exact characters it came from. With `trace`, the run also records what it
considered and rejected — the record most retrieval systems never keep.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .index import Bm25Index
from .tokenize import tokenize

#: How many candidates the trace shows before truncation to k.
TRACE_TOP = 20


@dataclass(frozen=True)
class Hit:
    """One retrieved passage."""

    handle: str
    score: float
    path: str
    start: int
    end: int
    sha256: str
    text: str

    def to_json(self) -> dict:
        return {
            "handle": self.handle,
            "score": round(self.score, 6),
            "path": self.path,
            "start": self.start,
            "end": self.end,
            "sha256": self.sha256,
            "snippet": self.text,
        }


@dataclass
class Trace:
    """Why the ranking came out the way it did."""

    query: str
    terms: list[str]
    term_matches: dict[str, int]
    considered: list[dict]
    returned: int
    tokenize_ms: float
    score_ms: float
    rank_ms: float

    def to_json(self) -> dict:
        return {
            "query": self.query,
            "terms": self.terms,
            "unique_terms": len(set(self.terms)),
            "term_matches": self.term_matches,
            "terms_not_found": [t for t, n in self.term_matches.items() if n == 0],
            "considered": self.considered,
            "returned": self.returned,
            "timings_ms": {
                "tokenize": round(self.tokenize_ms, 3),
                "score": round(self.score_ms, 3),
                "rank": round(self.rank_ms, 3),
            },
        }


def rank(index: Bm25Index, query_text: str) -> list[tuple[int, float]]:
    """``(chunk position, score)`` for every chunk scoring above zero, best first.

    Ties break on the citation handle, so the same index and query always produce
    the same order — a run artifact has to be reproducible.
    """
    scores = index.score(tokenize(query_text))
    hits = [(position, value) for position, value in enumerate(scores) if value > 0.0]
    hits.sort(key=lambda pair: (-pair[1], index.chunks[pair[0]].handle))
    return hits


def query(
    index: Bm25Index,
    query_text: str,
    k: int = 5,
    with_trace: bool = False,
) -> tuple[list[Hit], Trace | None]:
    """The top `k` passages for `query_text`, and optionally the trace.

    An empty list is a valid answer: it means no indexed token matched, which is a
    reportable outcome rather than an error.
    """
    started = time.perf_counter()
    terms = tokenize(query_text)
    after_tokenize = time.perf_counter()

    ranked = rank(index, query_text)
    after_score = time.perf_counter()

    top = ranked[:k]
    hits = [
        Hit(
            handle=record.handle,
            score=value,
            path=record.path,
            start=record.start,
            end=record.end,
            sha256=record.sha256,
            text=record.text,
        )
        for position, value in top
        for record in [index.chunks[position]]
    ]
    after_rank = time.perf_counter()

    if not with_trace:
        return hits, None

    trace = Trace(
        query=query_text,
        terms=terms,
        term_matches={term: len(index.postings.get(term, ())) for term in sorted(set(terms))},
        considered=[
            {"handle": index.chunks[position].handle, "score": round(value, 6)}
            for position, value in ranked[:TRACE_TOP]
        ],
        returned=len(hits),
        tokenize_ms=(after_tokenize - started) * 1000.0,
        score_ms=(after_score - after_tokenize) * 1000.0,
        rank_ms=(after_rank - after_score) * 1000.0,
    )
    return hits, trace
