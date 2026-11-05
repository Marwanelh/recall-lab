"""Tests for the evaluation layer.

Two behaviours here are the reason the module exists and are tested hardest: a case
citing an unresolvable passage must fail the run rather than score zero, and a case
whose passage has moved must be reported as stale rather than counted as a miss.
"""

import json
import tempfile
import unittest
from pathlib import Path

from recall_lab.chunk import Chunk
from recall_lab.evaluate import DatasetError, evaluate, load_dataset, load_lock, render_report
from recall_lab.index import Bm25Index


def make_chunk(path, text):
    return Chunk(path=path, start=0, end=len(text), text=text)


def small_index():
    """d0 = 'alpha beta beta', d1 = 'alpha gamma'."""
    return Bm25Index.build([make_chunk("a.md", "alpha beta beta"), make_chunk("b.md", "alpha gamma")])


HANDLE_A = "a.md#0-15"
HANDLE_B = "b.md#0-11"


class DatasetValidation(unittest.TestCase):
    def write(self, folder, lines):
        path = Path(folder) / "dataset.jsonl"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def test_reads_a_valid_dataset(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, [json.dumps({"id": "one", "question": "beta", "relevant": [HANDLE_A]})])
            cases = load_dataset(path)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].id, "one")

    def test_duplicate_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            row = json.dumps({"id": "same", "question": "q", "relevant": [HANDLE_A]})
            path = self.write(folder, [row, row])
            with self.assertRaises(DatasetError):
                load_dataset(path)

    def test_empty_question_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, [json.dumps({"id": "x", "question": "  ", "relevant": [HANDLE_A]})])
            with self.assertRaises(DatasetError):
                load_dataset(path)

    def test_no_relevant_handles_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, [json.dumps({"id": "x", "question": "q", "relevant": []})])
            with self.assertRaises(DatasetError):
                load_dataset(path)

    def test_invalid_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, ["{not json"])
            with self.assertRaises(DatasetError):
                load_dataset(path)

    def test_empty_dataset_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, [""])
            with self.assertRaises(DatasetError):
                load_dataset(path)


class MissingHandleFailsTheRun(unittest.TestCase):
    """A broken dataset must not be averaged in as a low score."""

    def test_unresolvable_handle_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            dataset = Path(folder) / "d.jsonl"
            dataset.write_text(
                json.dumps({"id": "gone", "question": "beta", "relevant": ["missing.md#0-10"]}),
                encoding="utf-8",
            )
            with self.assertRaises(DatasetError) as caught:
                evaluate(
                    small_index(),
                    load_dataset(dataset),
                    dataset_path=dataset,
                    index_path=dataset,
                )
        self.assertIn("not in the index", str(caught.exception))


class Metrics(unittest.TestCase):
    def artifact(self, cases):
        with tempfile.TemporaryDirectory() as folder:
            dataset = Path(folder) / "d.jsonl"
            dataset.write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")
            return evaluate(
                small_index(),
                load_dataset(dataset),
                dataset_path=dataset,
                index_path=dataset,
                revision="test",
            )

    def test_a_perfect_case_scores_one(self):
        artifact = self.artifact([{"id": "hit", "question": "gamma", "relevant": [HANDLE_B]}])
        self.assertEqual(artifact["aggregates"]["recall@1"], 1.0)
        self.assertEqual(artifact["aggregates"]["mrr"], 1.0)
        self.assertEqual(artifact["zero_cases"], [])

    def test_a_miss_scores_zero_and_is_listed(self):
        artifact = self.artifact([{"id": "miss", "question": "gamma", "relevant": [HANDLE_A]}])
        self.assertEqual(artifact["aggregates"]["recall@1"], 0.0)
        self.assertEqual(artifact["aggregates"]["mrr"], 0.0)
        self.assertEqual(artifact["zero_cases"], ["miss"])

    def test_recall_is_a_fraction_of_the_relevant_set(self):
        """'alpha' ranks b before a, so at K=1 half the relevant set is found."""
        artifact = self.artifact([{"id": "both", "question": "alpha", "relevant": [HANDLE_A, HANDLE_B]}])
        self.assertEqual(artifact["aggregates"]["recall@1"], 0.5)
        self.assertEqual(artifact["aggregates"]["recall@5"], 1.0)
        self.assertEqual(artifact["aggregates"]["mrr"], 1.0)

    def test_aggregates_average_over_cases(self):
        artifact = self.artifact(
            [
                {"id": "hit", "question": "gamma", "relevant": [HANDLE_B]},
                {"id": "miss", "question": "gamma", "relevant": [HANDLE_A]},
            ]
        )
        self.assertEqual(artifact["aggregates"]["recall@5"], 0.5)
        self.assertEqual(artifact["aggregates"]["cases"], 2)
        self.assertEqual(artifact["aggregates"]["cases_scored"], 2)


class StaleCases(unittest.TestCase):
    def test_a_moved_handle_is_excluded_and_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            dataset = Path(folder) / "d.jsonl"
            dataset.write_text(
                json.dumps({"id": "stale", "question": "gamma", "relevant": [HANDLE_B]}), encoding="utf-8"
            )
            lock = Path(folder) / "d.lock.json"
            lock.write_text(json.dumps({HANDLE_B: "a-different-hash"}), encoding="utf-8")

            artifact = evaluate(
                small_index(),
                load_dataset(dataset),
                dataset_path=dataset,
                index_path=dataset,
                lock_path=lock,
                revision="test",
            )
        self.assertTrue(artifact["stale_check"])
        self.assertEqual([row["id"] for row in artifact["stale_cases"]], ["stale"])
        self.assertEqual(artifact["aggregates"]["cases_scored"], 0)
        self.assertIsNone(artifact["aggregates"]["recall@1"])

    def test_a_matching_lock_scores_normally(self):
        index = small_index()
        with tempfile.TemporaryDirectory() as folder:
            dataset = Path(folder) / "d.jsonl"
            dataset.write_text(
                json.dumps({"id": "fresh", "question": "gamma", "relevant": [HANDLE_B]}), encoding="utf-8"
            )
            lock = Path(folder) / "d.lock.json"
            lock.write_text(json.dumps(index.sha_by_handle()), encoding="utf-8")

            artifact = evaluate(
                index,
                load_dataset(dataset),
                dataset_path=dataset,
                index_path=dataset,
                lock_path=lock,
                revision="test",
            )
        self.assertEqual(artifact["stale_cases"], [])
        self.assertEqual(artifact["aggregates"]["cases_scored"], 1)

    def test_no_lock_means_no_stale_check(self):
        artifact_cases = [{"id": "x", "question": "gamma", "relevant": [HANDLE_B]}]
        with tempfile.TemporaryDirectory() as folder:
            dataset = Path(folder) / "d.jsonl"
            dataset.write_text(json.dumps(artifact_cases[0]), encoding="utf-8")
            artifact = evaluate(
                small_index(),
                load_dataset(dataset),
                dataset_path=dataset,
                index_path=dataset,
                lock_path=Path(folder) / "absent.lock.json",
                revision="test",
            )
        self.assertFalse(artifact["stale_check"])

    def test_missing_lock_file_reads_as_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(load_lock(Path(folder) / "nope.json"), {})


class Artifact(unittest.TestCase):
    def build(self):
        with tempfile.TemporaryDirectory() as folder:
            dataset = Path(folder) / "d.jsonl"
            dataset.write_text(
                json.dumps({"id": "hit", "question": "gamma", "relevant": [HANDLE_B]}), encoding="utf-8"
            )
            return evaluate(
                small_index(),
                load_dataset(dataset),
                dataset_path=dataset,
                index_path=dataset,
                revision="deadbeef",
            )

    def test_records_the_inputs_that_produced_it(self):
        artifact = self.build()
        self.assertEqual(artifact["code_revision"], "deadbeef")
        self.assertIn("sha256", artifact["dataset"])
        self.assertIn("sha256", artifact["index"])
        self.assertEqual(artifact["config"]["k1"], 1.2)
        self.assertEqual(artifact["config"]["b"], 0.75)
        self.assertEqual(artifact["config"]["k_values"], [1, 5, 10])
        self.assertEqual(artifact["index_chunks"], 2)

    def test_keeps_per_case_detail(self):
        row = self.build()["per_case"][0]
        self.assertEqual(row["id"], "hit")
        self.assertEqual(row["first_relevant_rank"], 1)
        self.assertIn("top", row)

    def test_report_renders_without_placeholder_leakage(self):
        report = render_report(self.build())
        self.assertIn("Recall@1", report)
        self.assertIn("Cases that found nothing", report)
        self.assertIn("None — every case found a relevant passage", report)


if __name__ == "__main__":
    unittest.main()
