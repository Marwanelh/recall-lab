"""Tokenisation.

The one place the definition of a "word" lives, so indexing and querying can
never disagree about it. ADR-0004: no stemming, no stopword list.
"""

from __future__ import annotations

import re

#: A token is a run of lowercased ASCII letters and digits; everything else separates.
_WORD = re.compile(r"[a-z0-9]+")

#: One-character tokens are dropped: they carry almost no signal and inflate the
#: posting lists. Kept as a constant so the choice is visible and testable.
MIN_TOKEN_LENGTH = 2


def tokenize(text: str) -> list[str]:
    """The tokens of `text`, in order, lowercased.

    Repeated tokens are kept: the caller decides whether term frequency in the
    query matters (score() uses unique terms).
    """
    return [word for word in _WORD.findall(text.lower()) if len(word) >= MIN_TOKEN_LENGTH]
