"""Tests for the BM25 index and the query path.

The scoring test pins the arithmetic to a value worked out by hand, so the formula
in the code and the formula in the SPEC cannot drift apart silently.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path

from recall_lab.chunk import Chunk
from recall_lab.index import B, K1, Bm25Index
from recall_lab.query import query, rank


def make_chunk(path, start, text):
    return Chunk(path=path, start=start, end=start + len(text), text=text)


def small_index():
    """Two documents: d0 = 'alpha beta beta', d1 = 'alpha gamma'."""
    return Bm25Index.build([make_chunk("a.md", 0, "alpha beta beta"), make_chunk("b.md", 0, "alpha gamma")])


class Scoring(unittest.TestCase):
    def test_hand_computed_score(self):
        """BM25('beta') on d0 = 'alpha beta beta' with N=2, avgdl=2.5.

        f=2, dl=3, n=1, N=2
        idf    = ln(1 + (2 - 1 + 0.5) / (1 + 0.5)) = ln(2)
        denom  = 2 + 1.2 * (1 - 0.75 + 0.75 * 3 / 2.5) = 3.38
        score  = ln(2) * (2 * 2.2) / 3.38
        """
        expected = math.log(2.0) * (2 * (K1 + 1)) / (2 + K1 * (1 - B + B * 3 / 2.5))
        scores = small_index().score(["beta"])
        self.assertAlmostEqual(scores[0], expected, places=9)
        self.assertAlmostEqual(scores[0], 0.902322, places=5)
        self.assertEqual(scores[1], 0.0)

    def test_rarer_terms_weigh_more(self):
        index = small_index()
        self.assertGreater(index.idf("beta"), index.idf("alpha"))

    def test_absent_term_scores_zero_everywhere(self):
        self.assertEqual(small_index().score(["nonexistent"]), [0.0, 0.0])

    def test_repeated_query_terms_count_once(self):
        index = small_index()
        self.assertEqual(index.score(["beta", "beta"]), index.score(["beta"]))

    def test_length_normalisation_penalises_longer_documents(self):
        short = make_chunk("s.md", 0, "alpha beta")
        long = make_chunk("l.md", 0, "alpha beta " + "filler " * 40)
        index = Bm25Index.build([short, long])
        score_short, score_long = index.score(["beta"])
        self.assertGreater(score_short, score_long)

    def test_term_frequency_saturates(self):
        once = make_chunk("a.md", 0, "alpha beta")
        twice = make_chunk("b.md", 0, "alpha beta beta")
        index = Bm25Index.build([once, twice])
        score_once, score_twice = index.score(["beta"])
        self.assertGreater(score_twice, score_once)
        self.assertLess(score_twice, 2 * score_once)

    def test_empty_index_scores_nothing(self):
        self.assertEqual(Bm25Index.build([]).score(["alpha"]), [])


class Building(unittest.TestCase):
    def test_duplicate_handles_are_rejected(self):
        duplicate = make_chunk("a.md", 0, "same")
        with self.assertRaises(ValueError):
            Bm25Index.build([duplicate, duplicate])

    def test_postings_and_lengths_are_consistent(self):
        index = small_index()
        self.assertEqual(index.n, 2)
        self.assertEqual(index.lengths, [3, 2])
        self.assertAlmostEqual(index.avgdl, 2.5)
        self.assertEqual(index.postings["beta"], [[0, 2]])
        self.assertEqual(sorted(index.postings["alpha"]), [[0, 1], [1, 1]])

    def test_handles_are_exposed(self):
        self.assertEqual(small_index().handles(), {"a.md#0-15", "b.md#0-11"})


class Persistence(unittest.TestCase):
    def test_save_load_round_trip_scores_identically(self):
        index = small_index()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.json"
            index.save(path)
            reloaded = Bm25Index.load(path)
        self.assertEqual(reloaded.score(["beta"]), index.score(["beta"]))
        self.assertEqual(reloaded.score(["alpha"]), index.score(["alpha"]))
        self.assertEqual(reloaded.avgdl, index.avgdl)
        self.assertEqual(reloaded.k1, index.k1)
        self.assertEqual(reloaded.b, index.b)
        self.assertEqual(reloaded.handles(), index.handles())

    def test_saved_file_is_readable_json_with_the_parameters(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.json"
            small_index().save(path)
            document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["k1"], K1)
        self.assertEqual(document["b"], B)
        self.assertEqual(document["n"], 2)
        self.assertIn("index_sha256", document)
        self.assertIn("postings", document)

    def test_index_hash_changes_when_content_changes(self):
        first = Bm25Index.build([make_chunk("a.md", 0, "alpha beta")])
        second = Bm25Index.build([make_chunk("a.md", 0, "alpha gamma")])
        self.assertNotEqual(first.index_sha256(), second.index_sha256())

    def test_index_hash_is_stable_for_equal_content(self):
        self.assertEqual(small_index().index_sha256(), small_index().index_sha256())


class Ranking(unittest.TestCase):
    def test_highest_score_first(self):
        index = Bm25Index.build(
            [
                make_chunk("irrelevant.md", 0, "unrelated filler words"),
                make_chunk("target.md", 0, "beta beta beta"),
            ]
        )
        hits, _ = query(index, "beta", k=2)
        self.assertEqual(hits[0].handle, "target.md#0-14")

    def test_zero_scoring_chunks_are_not_returned(self):
        hits, _ = query(small_index(), "gamma", k=5)
        self.assertEqual([hit.handle for hit in hits], ["b.md#0-11"])

    def test_no_match_returns_nothing_rather_than_failing(self):
        hits, _ = query(small_index(), "nothing matches this", k=5)
        self.assertEqual(hits, [])

    def test_order_is_deterministic_on_ties(self):
        """Equal scores break on the citation handle, so runs are reproducible."""
        index = Bm25Index.build([make_chunk("b.md", 0, "alpha"), make_chunk("a.md", 0, "alpha")])
        ranked = [index.chunks[position].handle for position, _ in rank(index, "alpha")]
        self.assertEqual(ranked, ["a.md#0-5", "b.md#0-5"])

    def test_k_limits_the_result_count(self):
        index = Bm25Index.build([make_chunk(f"{n}.md", 0, "shared term here") for n in range(10)])
        hits, _ = query(index, "shared", k=3)
        self.assertEqual(len(hits), 3)

    def test_hits_carry_their_citation(self):
        hit = query(small_index(), "gamma", k=1)[0][0]
        self.assertEqual(hit.handle, "b.md#0-11")
        self.assertEqual(hit.path, "b.md")
        self.assertEqual(hit.start, 0)
        self.assertEqual(hit.end, 11)
        self.assertTrue(hit.sha256)


class Tracing(unittest.TestCase):
    def test_trace_records_what_was_not_found(self):
        _, trace = query(small_index(), "beta missingterm", k=1, with_trace=True)
        self.assertIsNotNone(trace)
        assert trace is not None  # for the type checker
        payload = trace.to_json()
        self.assertIn("missingterm", payload["terms_not_found"])
        self.assertEqual(payload["term_matches"]["beta"], 1)
        self.assertGreaterEqual(payload["returned"], 1)

    def test_trace_keeps_candidates_beyond_k(self):
        index = Bm25Index.build([make_chunk(f"{n}.md", 0, "shared term") for n in range(30)])
        _, trace = query(index, "shared", k=1, with_trace=True)
        self.assertIsNotNone(trace)
        assert trace is not None
        self.assertGreater(len(trace.considered), 1)

    def test_no_trace_unless_asked(self):
        self.assertIsNone(query(small_index(), "beta", k=1)[1])


if __name__ == "__main__":
    unittest.main()
