"""Ingest: walk a folder, read text, cut it into chunks with verifiable offsets.

The offsets are the point. Every chunk records the half-open character range
``[start, end)`` into the *original* file such that ``original[start:end]`` is
exactly the chunk text. That invariant is what makes a citation checkable by a
human, and it is asserted in the tests.

Chunking is deterministic: the same file always produces the same chunks, in the
same order, with the same handles. See SPEC.md section 1.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

CHUNK_TARGET_CHARS = 800
CHUNK_OVERLAP_CHARS = 150

READABLE_SUFFIXES = frozenset({".md", ".txt"})
SKIP_DIRECTORIES = frozenset({"node_modules", "__pycache__", ".git", ".venv"})

#: A line that contains at least one non-whitespace character.
_CONTENT_LINE = re.compile(r"[^\n]*\S[^\n]*")


@dataclass(frozen=True)
class Chunk:
    """One passage, and where it came from."""

    path: str  # relative POSIX path of the source file
    start: int  # inclusive character offset into the file
    end: int  # exclusive character offset into the file
    text: str

    @property
    def handle(self) -> str:
        """The citation: ``notes/bm25.md#120-940``. See ADR-0003."""
        return f"{self.path}#{self.start}-{self.end}"

    @property
    def sha256(self) -> str:
        """Hash of the chunk text, so a moved handle can be detected as stale."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


# --- finding paragraphs, with offsets ---------------------------------------


def paragraph_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of the paragraphs in `text`.

    A paragraph is a run of consecutive non-blank lines; a blank line (two or
    more newlines between content) ends it. Spans are ordered and disjoint.
    """
    lines = [(m.start(), m.end()) for m in _CONTENT_LINE.finditer(text)]
    if not lines:
        return []

    spans: list[tuple[int, int]] = []
    para_start, para_end = lines[0]
    for line_start, line_end in lines[1:]:
        gap = text[para_end:line_start]
        if gap.count("\n") >= 2:
            spans.append((para_start, para_end))
            para_start, para_end = line_start, line_end
        else:
            para_end = line_end
    spans.append((para_start, para_end))
    return spans


def _split_oversized(text: str, start: int, end: int, target: int) -> list[tuple[int, int]]:
    """Cut a span longer than `target` into pieces of at most `target` characters.

    Breaks at the last space before the limit when there is one, so words stay
    whole; falls back to a hard cut when a single word is longer than the limit.
    """
    pieces: list[tuple[int, int]] = []
    while end - start > target:
        cut = start + target
        space = text.rfind(" ", start, cut)
        if space > start:
            cut = space
        pieces.append((start, cut))
        start = cut
        while start < end and text[start].isspace():
            start += 1
    if end > start:
        pieces.append((start, end))
    return pieces


def _pieces(text: str, target: int) -> list[tuple[int, int]]:
    """Paragraph spans, with any oversized paragraph split down to `target`."""
    pieces: list[tuple[int, int]] = []
    for start, end in paragraph_spans(text):
        pieces.extend(_split_oversized(text, start, end, target))
    return pieces


def chunk_text(
    text: str,
    target: int = CHUNK_TARGET_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[tuple[int, int]]:
    """The chunk boundaries of `text`, as ``(start, end)`` pairs.

    Grow a chunk paragraph by paragraph until the next one would pass `target`,
    emit it, then start the next one `overlap` characters before the end of the
    one just emitted so a fact spanning a boundary is not cut in half.

    Every chunk is at most `target` characters: when the overlap point leaves no
    room for the next paragraph, the next chunk simply starts at that paragraph
    instead and the overlap is dropped. Without that rule the loop could fail to
    advance.
    """
    if overlap >= target:
        raise ValueError("overlap must be smaller than target")

    pieces = _pieces(text, target)
    if not pieces:
        return []

    chunks: list[tuple[int, int]] = []
    start = pieces[0][0]
    end = pieces[0][1]
    i = 1

    while True:
        while i < len(pieces) and pieces[i][1] - start <= target:
            end = pieces[i][1]
            i += 1
        chunks.append((start, end))
        if i >= len(pieces):
            return chunks

        # Always move forward, even if the overlap is larger than the chunk.
        start = max(end - overlap, start + 1)
        end = start
        if pieces[i][1] - start > target:
            # No room for the next paragraph from the overlap point: drop the
            # overlap rather than emit a chunk longer than target.
            start = pieces[i][0]
            end = start


# --- reading a folder --------------------------------------------------------


def is_readable(path: Path, root: Path) -> bool:
    """Whether `path` is a document we ingest."""
    if not path.is_file() or path.suffix.lower() not in READABLE_SUFFIXES:
        return False
    return not any(
        part.startswith(".") or part in SKIP_DIRECTORIES for part in path.relative_to(root).parts
    )


def read_documents(root: str | Path) -> list[tuple[str, str]]:
    """``(relative_path, text)`` for every readable file under `root`.

    Sorted by relative POSIX path so ingestion order — and therefore chunk order
    and every offset — is reproducible on any machine.
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")

    paths = sorted(
        (p for p in root.rglob("*") if is_readable(p, root)),
        key=lambda p: p.relative_to(root).as_posix(),
    )
    return [(p.relative_to(root).as_posix(), p.read_text(encoding="utf-8", errors="replace")) for p in paths]


def chunk_documents(
    documents: list[tuple[str, str]],
    target: int = CHUNK_TARGET_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[Chunk]:
    """Chunk every document, dropping chunks with no alphanumeric character."""
    chunks: list[Chunk] = []
    for path, text in documents:
        for start, end in chunk_text(text, target, overlap):
            body = text[start:end]
            if not any(c.isalnum() for c in body):
                continue
            chunks.append(Chunk(path=path, start=start, end=end, text=body))
    return chunks


def chunk_folder(
    root: str | Path,
    target: int = CHUNK_TARGET_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[Chunk]:
    """Read a folder and chunk everything in it."""
    return chunk_documents(read_documents(root), target, overlap)
