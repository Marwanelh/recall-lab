"""Evaluate: score retrieval against a committed dataset, and write a run artifact.

Two rules shape everything here, both from ADR-0005:

1. A case whose relevant handle is **not in the index** fails the run. Scoring it
   zero would quietly turn a broken dataset into a bad metric, and a silently
   wrong number is the most expensive kind of evaluation bug.
2. A case whose relevant handle exists but whose text **has moved** is *stale*: it
   is excluded from the aggregate and listed. It is never scored as a miss and
   never silently dropped.

Every number this module reports is written into a JSON artifact alongside the
inputs that produced it, so it can be checked rather than believed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .index import Bm25Index
from .query import rank

#: The cut-offs reported for every run.
K_VALUES = (1, 5, 10)


class DatasetError(ValueError):
    """The dataset is unusable. Reported to the user, exit code 2."""


@dataclass(frozen=True)
class Case:
    """One question and the passages that genuinely answer it."""

    id: str
    question: str
    relevant: list[str]


def load_dataset(path: str | Path) -> list[Case]:
    """Read and validate a JSONL dataset.

    Raises `DatasetError` on anything that would make a score meaningless: a
    duplicate id, an empty question, or a case with no relevant passage.
    """
    source = Path(path)
    if not source.is_file():
        raise DatasetError(f"dataset not found: {source}")

    cases: list[Case] = []
    seen: set[str] = set()
    for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise DatasetError(f"{source}:{number}: not valid JSON ({error.msg})") from error
        if not isinstance(row, dict):
            raise DatasetError(f"{source}:{number}: expected an object")

        case_id = str(row.get("id") or "").strip()
        question = str(row.get("question") or "").strip()
        relevant = row.get("relevant")

        if not case_id:
            raise DatasetError(f"{source}:{number}: missing id")
        if case_id in seen:
            raise DatasetError(f"{source}:{number}: duplicate id {case_id!r}")
        if not question:
            raise DatasetError(f"{source}:{number}: case {case_id!r} has an empty question")
        if not isinstance(relevant, list) or not all(isinstance(h, str) and h.strip() for h in relevant):
            raise DatasetError(f"{source}:{number}: case {case_id!r} needs a non-empty list of handles")
        if not relevant:
            raise DatasetError(f"{source}:{number}: case {case_id!r} has no relevant passages")

        seen.add(case_id)
        cases.append(Case(id=case_id, question=question, relevant=list(relevant)))

    if not cases:
        raise DatasetError(f"dataset is empty: {source}")
    return cases


def load_lock(path: str | Path) -> dict[str, str]:
    """Read the committed handle->sha map, or an empty map when there is none."""
    source = Path(path)
    if not source.is_file():
        return {}
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DatasetError(f"lock file must be an object of handle -> sha256: {source}")
    return {str(handle): str(digest) for handle, digest in data.items()}


def sha256_file(path: str | Path) -> str:
    """Hash a file's bytes, so an artifact can name the exact inputs it used."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_revision(root: str | Path | None = None) -> str:
    """The git revision of the working tree, or "unknown" outside a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root or Path.cwd()),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _validate_handles(index: Bm25Index, cases: list[Case]) -> None:
    """Fail the run when a case cites a passage the index cannot resolve."""
    known = index.handles()
    missing = sorted({handle for case in cases for handle in case.relevant if handle not in known})
    if missing:
        shown = "\n  ".join(missing[:10])
        more = f"\n  ... and {len(missing) - 10} more" if len(missing) > 10 else ""
        raise DatasetError(
            "dataset cites passages that are not in the index — the dataset and the "
            f"corpus disagree:\n  {shown}{more}"
        )


def _rank_of_first_relevant(ranked: list[str], relevant: set[str], within: int) -> int | None:
    """1-based rank of the first relevant passage in the top `within`, or None."""
    for position, handle in enumerate(ranked[:within], start=1):
        if handle in relevant:
            return position
    return None


def evaluate(
    index: Bm25Index,
    cases: list[Case],
    dataset_path: str | Path,
    index_path: str | Path,
    lock_path: str | Path | None = None,
    k_values: tuple[int, ...] = K_VALUES,
    revision: str | None = None,
) -> dict:
    """Score every case and return the run artifact as a plain dict."""
    _validate_handles(index, cases)

    lock = load_lock(lock_path) if lock_path is not None else {}
    current_sha = index.sha_by_handle()
    largest_k = max(k_values)

    per_case: list[dict] = []
    stale_cases: list[dict] = []
    totals = {k: 0.0 for k in k_values}
    reciprocal_total = 0.0
    scored = 0

    for case in cases:
        stale = [handle for handle in case.relevant if handle in lock and lock[handle] != current_sha[handle]]
        if stale:
            stale_cases.append({"id": case.id, "handles": stale})
            continue

        ranked = [index.chunks[position].handle for position, _ in rank(index, case.question)]
        relevant = set(case.relevant)
        first = _rank_of_first_relevant(ranked, relevant, largest_k)

        recall = {
            f"recall@{k}": round(_hits_in(ranked, relevant, k) / len(relevant), 6) for k in k_values
        }
        for k in k_values:
            totals[k] += _hits_in(ranked, relevant, k) / len(relevant)
        reciprocal_total += (1.0 / first) if first else 0.0
        scored += 1

        per_case.append(
            {
                "id": case.id,
                "question": case.question,
                "relevant": case.relevant,
                "returned": len(ranked),
                "first_relevant_rank": first,
                **recall,
                "top": ranked[:largest_k],
            }
        )

    aggregates: dict = {"cases": len(cases), "cases_scored": scored}
    if scored:
        for k in k_values:
            aggregates[f"recall@{k}"] = round(totals[k] / scored, 6)
        aggregates["mrr"] = round(reciprocal_total / scored, 6)
    else:
        for k in k_values:
            aggregates[f"recall@{k}"] = None
        aggregates["mrr"] = None

    return {
        "tool": "recall-lab",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_revision": revision if revision is not None else code_revision(),
        "dataset": {"path": str(dataset_path), "sha256": sha256_file(dataset_path)},
        "index": {"path": str(index_path), "sha256": index.index_sha256()},
        "config": {
            "k1": index.k1,
            "b": index.b,
            "chunk_target_chars": index.chunk_target_chars,
            "chunk_overlap_chars": index.chunk_overlap_chars,
            "k_values": list(k_values),
            "tokenizer": "lowercase, split on [^a-z0-9], drop length < 2",
        },
        "index_chunks": index.n,
        "stale_check": bool(lock),
        "stale_cases": stale_cases,
        "aggregates": aggregates,
        "zero_cases": [row["id"] for row in per_case if row["first_relevant_rank"] is None],
        "per_case": per_case,
    }


def _hits_in(ranked: list[str], relevant: set[str], k: int) -> int:
    """How many distinct relevant passages appear in the top `k`."""
    return len(set(ranked[:k]) & relevant)


def render_report(artifact: dict) -> str:
    """The run artifact as markdown, for committing next to the JSON."""
    aggregates = artifact["aggregates"]
    config = artifact["config"]
    k_values = config["k_values"]

    lines = [
        "# Retrieval evaluation",
        "",
        f"Generated {artifact['generated_at']} · code `{artifact['code_revision'][:12]}`",
        "",
        f"{aggregates['cases']} cases · {artifact['index_chunks']} indexed passages · "
        f"chunk {config['chunk_target_chars']}/{config['chunk_overlap_chars']} · "
        f"k1={config['k1']} b={config['b']}",
        "",
        "| metric | value |",
        "|---|---|",
    ]
    for k in k_values:
        value = aggregates.get(f"recall@{k}")
        lines.append(f"| Recall@{k} | {_fmt(value)} |")
    lines.append(f"| MRR | {_fmt(aggregates.get('mrr'))} |")
    lines += [
        "",
        "## Cases that found nothing",
        "",
    ]
    if artifact["zero_cases"]:
        lines += [f"- `{case_id}`" for case_id in artifact["zero_cases"]]
    else:
        lines.append("None — every case found a relevant passage in its top results.")

    if artifact["stale_cases"]:
        lines += ["", "## Stale cases (excluded, not scored)", ""]
        lines += [f"- `{row['id']}` — handles moved: {', '.join(row['handles'])}" for row in artifact["stale_cases"]]

    lines += [
        "",
        "## Inputs",
        "",
        f"- dataset `{artifact['dataset']['path']}` sha256 `{artifact['dataset']['sha256'][:16]}…`",
        f"- index sha256 `{artifact['index']['sha256'][:16]}…`",
        f"- stale check: {'on' if artifact['stale_check'] else 'off (no lock file committed)'}",
        "",
        "Reproduce with:",
        "",
        "```",
        f"python -m recall_lab evaluate {artifact['index']['path']} {artifact['dataset']['path']} "
        f"--report {artifact['dataset']['path'].rsplit('/', 1)[0]}/REPORT.md",
        "```",
        "",
    ]
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"
