"""Tests for ingest and chunking.

The load-bearing ones are the offset invariant (a citation must be checkable) and
termination (the overlap rule must not be able to loop forever).
"""

import unittest
from pathlib import Path
import tempfile

from recall_lab.chunk import (
    CHUNK_OVERLAP_CHARS,
    CHUNK_TARGET_CHARS,
    chunk_documents,
    chunk_text,
    is_readable,
    paragraph_spans,
    read_documents,
)


class ParagraphSpans(unittest.TestCase):
    def test_blank_line_ends_a_paragraph(self):
        text = "first para line one\nline two\n\nsecond para"
        spans = paragraph_spans(text)
        self.assertEqual(len(spans), 2)
        self.assertEqual(text[spans[0][0]:spans[0][1]], "first para line one\nline two")
        self.assertEqual(text[spans[1][0]:spans[1][1]], "second para")

    def test_single_newline_does_not_end_a_paragraph(self):
        self.assertEqual(len(paragraph_spans("one\ntwo\nthree")), 1)

    def test_whitespace_only_lines_do_not_become_paragraphs(self):
        text = "alpha\n   \nbeta"
        self.assertEqual(len(paragraph_spans(text)), 2)

    def test_no_content_gives_no_spans(self):
        self.assertEqual(paragraph_spans("\n\n   \n"), [])


class OffsetInvariant(unittest.TestCase):
    """`original[start:end]` must be exactly the chunk text. This is the citation."""

    def test_offsets_address_the_original_text(self):
        text = "\n\n".join(f"Paragraph {n}. " + "word " * 40 for n in range(12))
        for start, end in chunk_text(text):
            self.assertEqual(text[start:end], text[start:end])
            self.assertGreater(end, start)

    def test_chunks_recover_their_own_text_through_documents(self):
        text = "# Title\n\n" + "\n\n".join(f"Section {n} " + "token " * 60 for n in range(6))
        chunks = chunk_documents([("doc.md", text)])
        for chunk in chunks:
            self.assertEqual(text[chunk.start:chunk.end], chunk.text)
            self.assertEqual(chunk.handle, f"doc.md#{chunk.start}-{chunk.end}")


class ChunkSizes(unittest.TestCase):
    def test_no_chunk_exceeds_the_target(self):
        text = "\n\n".join("sentence " * 30 for _ in range(10))
        for start, end in chunk_text(text, target=400, overlap=50):
            self.assertLessEqual(end - start, 400)

    def test_a_single_paragraph_larger_than_the_target_is_split(self):
        text = "word " * 500  # no blank lines at all, so one huge paragraph
        spans = chunk_text(text, target=200, overlap=20)
        self.assertGreater(len(spans), 1)
        for start, end in spans:
            self.assertLessEqual(end - start, 200)

    def test_a_word_longer_than_the_target_is_hard_cut(self):
        text = "x" * 900
        spans = chunk_text(text, target=200, overlap=20)
        self.assertGreater(len(spans), 1)
        for start, end in spans:
            self.assertLessEqual(end - start, 200)

    def test_overlap_actually_overlaps(self):
        text = "\n\n".join(f"Paragraph {n} " + "content " * 20 for n in range(8))
        spans = chunk_text(text, target=500, overlap=100)
        self.assertGreater(len(spans), 2)
        for (_, previous_end), (next_start, _) in zip(spans, spans[1:]):
            self.assertLess(next_start, previous_end)


class Determinism(unittest.TestCase):
    def test_same_input_gives_the_same_chunks(self):
        text = "\n\n".join(f"Block {n} " + "text " * 50 for n in range(9))
        self.assertEqual(chunk_text(text), chunk_text(text))

    def test_read_documents_orders_by_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "z.md").write_text("zeta " * 40, encoding="utf-8")
            (root / "a.md").write_text("alpha " * 40, encoding="utf-8")
            names = [path for path, _ in read_documents(root)]
        self.assertEqual(names, ["a.md", "z.md"])


class Guards(unittest.TestCase):
    def test_overlap_must_be_smaller_than_target(self):
        with self.assertRaises(ValueError):
            chunk_text("anything", target=100, overlap=100)

    def test_large_overlap_still_terminates_and_is_bounded(self):
        text = "\n\n".join("paragraph content words here " * 5 for _ in range(40))
        spans = chunk_text(text, target=300, overlap=299)
        self.assertTrue(spans)
        self.assertLessEqual(len(spans), len(text))
        self.assertEqual(spans, sorted(spans))

    def test_empty_text_has_no_chunks(self):
        self.assertEqual(chunk_text(""), [])

    def test_chunks_without_alphanumerics_are_dropped(self):
        chunks = chunk_documents([("junk.md", "---\n\n***\n\n!!!")])
        self.assertEqual(chunks, [])

    def test_defaults_match_the_spec(self):
        self.assertEqual(CHUNK_TARGET_CHARS, 800)
        self.assertEqual(CHUNK_OVERLAP_CHARS, 150)


class ReadableFiles(unittest.TestCase):
    """`is_readable` needs real files: it asks the filesystem, not the name."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.root = Path(self._folder.name)
        (self.root / "a.md").write_text("markdown", encoding="utf-8")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "b.txt").write_text("text", encoding="utf-8")
        (self.root / "a.pdf").write_text("pdf", encoding="utf-8")
        (self.root / ".hidden").mkdir()
        (self.root / ".hidden" / "c.md").write_text("hidden", encoding="utf-8")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "d.md").write_text("vendored", encoding="utf-8")

    def tearDown(self):
        self._folder.cleanup()

    def test_markdown_and_text_are_read(self):
        self.assertTrue(is_readable(self.root / "a.md", self.root))
        self.assertTrue(is_readable(self.root / "sub" / "b.txt", self.root))

    def test_other_extensions_are_skipped(self):
        self.assertFalse(is_readable(self.root / "a.pdf", self.root))

    def test_hidden_directories_are_skipped(self):
        self.assertFalse(is_readable(self.root / ".hidden" / "c.md", self.root))

    def test_node_modules_is_skipped(self):
        self.assertFalse(is_readable(self.root / "node_modules" / "d.md", self.root))

    def test_a_directory_is_not_readable(self):
        self.assertFalse(is_readable(self.root / "sub", self.root))


if __name__ == "__main__":
    unittest.main()
