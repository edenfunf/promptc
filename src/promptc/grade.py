"""Efficiency Grade calculation.

Bloat Ratio (v0.1 definition):
    bloat_ratio = duplicate_tokens / total_tokens

The original checklist §2.2 defined it as
``(duplicate_tokens + low_value_tokens) / total_tokens``, but v0.1 has no
dead-code elimination / low-value detection, so that term drops out. The
Ratio → Letter thresholds are preserved:

    A:  ratio <  5%
    B:  5%  <=  ratio <  15%
    C:  15% <=  ratio <  25%
    D:  25% <=  ratio <  40%
    F:  40% <=  ratio

Each letter (except F) carries a ``+`` / ``-`` modifier indicating the
upper or lower half of its bracket. ``+`` means lower bloat (better);
``-`` means higher bloat (worse). Example: D+ is 25-32.5%, D- is
32.5-40%. F carries no modifier.
"""

from __future__ import annotations

from dataclasses import dataclass

_BRACKETS: list[tuple[str, float, float]] = [
    ("A", 0.00, 0.05),
    ("B", 0.05, 0.15),
    ("C", 0.15, 0.25),
    ("D", 0.25, 0.40),
    ("F", 0.40, 1.01),
]


@dataclass(frozen=True)
class Grade:
    letter: str
    modifier: str
    bloat_ratio: float

    @property
    def display(self) -> str:
        return f"{self.letter}{self.modifier}"

    @property
    def color(self) -> str:
        return {
            "A": "bright_green",
            "B": "green",
            "C": "yellow",
            "D": "red",
            "F": "bright_red",
        }.get(self.letter, "white")


def compute_grade(bloat_ratio: float) -> Grade:
    """Return a :class:`Grade` for the given bloat ratio in [0, 1]."""
    ratio = max(0.0, min(bloat_ratio, 1.0))

    for letter, low, high in _BRACKETS:
        if ratio < high:
            if letter == "F":
                return Grade(letter=letter, modifier="", bloat_ratio=ratio)
            mid = (low + high) / 2
            modifier = "+" if ratio < mid else "-"
            return Grade(letter=letter, modifier=modifier, bloat_ratio=ratio)

    return Grade(letter="F", modifier="", bloat_ratio=ratio)
