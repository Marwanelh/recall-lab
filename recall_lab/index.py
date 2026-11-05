"""The BM25 index: build it, save it as readable JSON, load it, score with it.

One indexed document is one chunk. The arithmetic is in SPEC.md section 3 and is
deliberately short enough to check by hand against a saved index file.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .chunk import CHUNK_OVERLAP_CHARS, CHUNK_TARGET_CHARS, Chunk
from .tokenize import tokenize

K1 = 1.2
B = 0.75

INDEX_FORMAT = 1


@dataclass
class ChunkRecord:
    """What the index remembers about one chunk."""

    handle: str
    path: str
    start: int
    end: int
    sha256: str
    tokens: int
    text: str

    def to_json(self) -> dict:
        return {
            "handle": self.handle,
            "path": self.path,
            "start": self.start,
            "end": self.end,
            "sha256": self.sha256,
            "tokens": self.tokens,
            "text": self.text,
        }

    @classmethod
    def from_json(cls, data: dict) -> "ChunkRecord":
        return cls(
            handle=data["handle"],
            path=data["path"],
            start=data["start"],
            end=data["end"],
            sha256=data["sha256"],
            tokens=data["tokens"],
            text=data["text"],
        )


@dataclass
class Bm25Index:
    """An inverted index over chunks, scored with BM25."""

    chunks: list[ChunkRecord] = field(default_factory=list)
    #: term -> [(chunk position, term frequency)], sorted by position
    postings: dict[str, list[list[int]]] = field(default_factory=dict)
    lengths: list[int] = field(default_factory=list)
    avgdl: float = 0.0
    k1: float = K1
    b: float = B
    chunk_target_chars: int = CHUNK_TARGET_CHARS
    chunk_overlap_chars: int = CHUNK_OVERLAP_CHARS

    @property
    def n(self) -> int:
        """Number of indexed chunks."""
        return len(self.chunks)

    # --- building -----------------------------------------------------------

    @classmethod
    def build(
        cls,
        chunks: list[Chunk],
        k1: float = K1,
        b: float = B,
        chunk_target_chars: int = CHUNK_TARGET_CHARS,
        chunk_overlap_chars: int = CHUNK_OVERLAP_CHARS,
    ) -> "Bm25Index":
        """Index `chunks`. Raises on duplicate handles — they would be unreachable."""
        records: list[ChunkRecord] = []
        postings: dict[str, list[list[int]]] = {}
        lengths: list[int] = []
        seen: set[str] = set()

        for position, chunk in enumerate(chunks):
            if chunk.handle in seen:
                raise ValueError(f"duplicate chunk handle: {chunk.handle}")
            seen.add(chunk.handle)

            terms = tokenize(chunk.text)
            records.append(
                ChunkRecord(
                    handle=chunk.handle,
                    path=chunk.path,
                    start=chunk.start,
                    end=chunk.end,
                    sha256=chunk.sha256,
                    tokens=len(terms),
                    text=chunk.text,
                )
            )
            lengths.append(len(terms))

            counts: dict[str, int] = {}
            for term in terms:
                counts[term] = counts.get(term, 0) + 1
            for term, count in counts.items():
                postings.setdefault(term, []).append([position, count])

        average = (sum(lengths) / len(lengths)) if lengths else 0.0
        return cls(
            chunks=records,
            postings=postings,
            lengths=lengths,
            avgdl=average,
            k1=k1,
            b=b,
            chunk_target_chars=chunk_target_chars,
            chunk_overlap_chars=chunk_overlap_chars,
        )

    # --- scoring ------------------------------------------------------------

    def idf(self, term: str) -> float:
        """Inverse document frequency of `term`, using the +0.5 smoothed form."""
        n_term = len(self.postings.get(term, ()))
        if n_term == 0:
            return 0.0
        return math.log(1.0 + (self.n - n_term + 0.5) / (n_term + 0.5))

    def score(self, terms: list[str]) -> list[float]:
        """BM25 score per indexed chunk for `terms`.

        Repeated query terms are counted once, so a query is scored on which
        terms it contains rather than on how often they are typed.
        """
        scores = [0.0] * self.n
        if self.avgdl == 0.0:
            return scores

        for term in set(terms):
            postings = self.postings.get(term)
            if not postings:
                continue
            weight = self.idf(term)
            for position, frequency in postings:
                length = self.lengths[position]
                denominator = frequency + self.k1 * (1.0 - self.b + self.b * length / self.avgdl)
                scores[position] += weight * (frequency * (self.k1 + 1.0)) / denominator
        return scores

    def handles(self) -> set[str]:
        """Every handle in the index."""
        return {record.handle for record in self.chunks}

    def sha_by_handle(self) -> dict[str, str]:
        """Handle -> content hash, for detecting a dataset case that went stale."""
        return {record.handle: record.sha256 for record in self.chunks}

    # --- persistence --------------------------------------------------------

    def payload(self) -> dict:
        """The serialisable form, without the self-referential hash."""
        return {
            "index_format": INDEX_FORMAT,
            "k1": self.k1,
            "b": self.b,
            "chunk_target_chars": self.chunk_target_chars,
            "chunk_overlap_chars": self.chunk_overlap_chars,
            "n": self.n,
            "avgdl": self.avgdl,
            "lengths": self.lengths,
            "chunks": [record.to_json() for record in self.chunks],
            "postings": {term: plist for term, plist in sorted(self.postings.items())},
        }

    def index_sha256(self) -> str:
        """A stable hash of everything a run needs to record. See SPEC section 7."""
        import hashlib

        canonical = json.dumps(self.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def save(self, path: str | Path) -> None:
        """Write the index as readable JSON, then verify it reads back identically."""
        document = dict(self.payload())
        document["index_sha256"] = self.index_sha256()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, indent=1, ensure_ascii=False, sort_keys=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Bm25Index":
        """Read an index written by `save`."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            chunks=[ChunkRecord.from_json(record) for record in data["chunks"]],
            postings={term: [list(pair) for pair in plist] for term, plist in data["postings"].items()},
            lengths=list(data["lengths"]),
            avgdl=float(data["avgdl"]),
            k1=float(data["k1"]),
            b=float(data["b"]),
            chunk_target_chars=int(data["chunk_target_chars"]),
            chunk_overlap_chars=int(data["chunk_overlap_chars"]),
        )
