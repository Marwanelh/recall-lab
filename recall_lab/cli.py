"""Command line: index a folder, query an index, evaluate against a dataset.

Exit codes: 0 success, 1 usage error, 2 the inputs are not usable (bad dataset,
unresolvable citation). Everything a run produces is written to a file and its
path is printed — no result exists only on the terminal.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .chunk import CHUNK_OVERLAP_CHARS, CHUNK_TARGET_CHARS, chunk_folder
from .evaluate import K_VALUES, DatasetError, evaluate, load_dataset, render_report
from .index import Bm25Index
from .query import query


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recall-lab",
        description="Retrieve passages from your own documents, and measure how well.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="index a folder of .md and .txt files")
    index_parser.add_argument("docs", help="folder to index")
    index_parser.add_argument("--out", default="index.json", help="where to write the index")
    index_parser.add_argument("--chunk-chars", type=int, default=CHUNK_TARGET_CHARS)
    index_parser.add_argument("--overlap-chars", type=int, default=CHUNK_OVERLAP_CHARS)

    query_parser = subparsers.add_parser("query", help="print the top passages for a question")
    query_parser.add_argument("index", help="an index written by `index`")
    query_parser.add_argument("question")
    query_parser.add_argument("-k", type=int, default=5, help="how many passages to return")
    query_parser.add_argument("--trace", action="store_true", help="record why the ranking came out this way")
    query_parser.add_argument("--json", action="store_true", help="print the results as JSON")

    evaluate_parser = subparsers.add_parser("evaluate", help="score retrieval against a dataset")
    evaluate_parser.add_argument("index", help="an index written by `index`")
    evaluate_parser.add_argument("dataset", help="a JSONL dataset of question -> relevant handles")
    evaluate_parser.add_argument("--out", default="runs/run.json", help="where to write the run artifact")
    evaluate_parser.add_argument("--report", help="also write the artifact as markdown here")
    evaluate_parser.add_argument(
        "--lock",
        help="handle->sha256 map used to detect stale cases (default: <dataset>.lock.json)",
    )

    return parser


def run_index(args: argparse.Namespace) -> int:
    if args.chunk_chars <= 0:
        print("error: --chunk-chars must be positive", file=sys.stderr)
        return 1
    if not 0 <= args.overlap_chars < args.chunk_chars:
        print("error: --overlap-chars must be >= 0 and smaller than --chunk-chars", file=sys.stderr)
        return 1

    try:
        chunks = chunk_folder(args.docs, args.chunk_chars, args.overlap_chars)
    except (NotADirectoryError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if not chunks:
        print(f"error: no .md or .txt documents found under {args.docs}", file=sys.stderr)
        return 2

    index = Bm25Index.build(
        chunks,
        chunk_target_chars=args.chunk_chars,
        chunk_overlap_chars=args.overlap_chars,
    )
    index.save(args.out)

    files = len({chunk.path for chunk in chunks})
    print(f"indexed {len(chunks)} passages from {files} documents -> {args.out}")
    print(f"  vocabulary {len(index.postings)} terms · avg length {index.avgdl:.1f} tokens")
    print(f"  index sha256 {index.index_sha256()[:16]}…")
    return 0


def run_query(args: argparse.Namespace) -> int:
    try:
        index = Bm25Index.load(args.index)
    except (OSError, ValueError, KeyError) as error:
        print(f"error: could not read index {args.index}: {error}", file=sys.stderr)
        return 2

    hits, trace = query(index, args.question, k=args.k, with_trace=args.trace)

    if args.json:
        payload: dict = {"query": args.question, "k": args.k, "hits": [hit.to_json() for hit in hits]}
        if trace is not None:
            payload["trace"] = trace.to_json()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if not hits:
        print("no passage scored above zero — no indexed term from the question is in the corpus")
        return 0

    for position, hit in enumerate(hits, start=1):
        preview = " ".join(hit.text.split())
        if len(preview) > 110:
            preview = preview[:107] + "…"
        print(f"{position:2}. {hit.score:.3f}  {hit.handle}")
        print(f"     {preview}")

    if trace is not None:
        missing = trace.to_json()["terms_not_found"]
        print("")
        print(f"trace: {len(trace.terms)} tokens ({trace.to_json()['unique_terms']} unique), "
              f"{len(trace.considered)} passages scored above zero, {trace.returned} returned")
        print(f"       not found in the corpus: {', '.join(missing) if missing else 'none'}")
        print(f"       timings: tokenize {trace.tokenize_ms:.2f}ms · score {trace.score_ms:.2f}ms · "
              f"rank {trace.rank_ms:.2f}ms")
    return 0


def run_evaluate(args: argparse.Namespace) -> int:
    try:
        index = Bm25Index.load(args.index)
    except (OSError, ValueError, KeyError) as error:
        print(f"error: could not read index {args.index}: {error}", file=sys.stderr)
        return 2

    lock_path = args.lock or str(Path(args.dataset).with_suffix(".lock.json"))

    try:
        cases = load_dataset(args.dataset)
        artifact = evaluate(
            index,
            cases,
            dataset_path=args.dataset,
            index_path=args.index,
            lock_path=lock_path,
            k_values=K_VALUES,
        )
    except DatasetError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    aggregates = artifact["aggregates"]
    print(f"{aggregates['cases']} cases · {aggregates['cases_scored']} scored · "
          f"{artifact['index_chunks']} passages")
    for k in K_VALUES:
        print(f"  Recall@{k:<2} {aggregates[f'recall@{k}']:.3f}")
    print(f"  MRR      {aggregates['mrr']:.3f}")
    if artifact["stale_cases"]:
        print(f"  {len(artifact['stale_cases'])} stale case(s) excluded — see the artifact")
    if artifact["zero_cases"]:
        print(f"  {len(artifact['zero_cases'])} case(s) found nothing: {', '.join(artifact['zero_cases'])}")
    print(f"artifact -> {out_path}")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report(artifact), encoding="utf-8")
        print(f"report   -> {report_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"index": run_index, "query": run_query, "evaluate": run_evaluate}
    return handlers[args.command](args)
