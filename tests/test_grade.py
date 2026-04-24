from __future__ import annotations

import pytest

from promptc.grade import compute_grade


@pytest.mark.parametrize(
    "ratio,expected",
    [
        (0.00, "A+"),
        (0.01, "A+"),
        (0.024, "A+"),
        (0.025, "A-"),
        (0.049, "A-"),
        (0.05, "B+"),
        (0.099, "B+"),
        (0.10, "B-"),
        (0.149, "B-"),
        (0.15, "C+"),
        (0.199, "C+"),
        (0.20, "C-"),
        (0.249, "C-"),
        (0.25, "D+"),
        (0.324, "D+"),
        (0.325, "D-"),
        (0.399, "D-"),
        (0.40, "F"),
        (0.50, "F"),
        (0.99, "F"),
        (1.00, "F"),
    ],
)
def test_grade_boundaries(ratio: float, expected: str) -> None:
    assert compute_grade(ratio).display == expected


def test_grade_clamps_negative_to_zero() -> None:
    assert compute_grade(-0.5).display == "A+"


def test_grade_clamps_above_one_to_one() -> None:
    assert compute_grade(5.0).display == "F"


def test_grade_stores_original_ratio_clamped() -> None:
    g = compute_grade(0.273)
    assert g.bloat_ratio == 0.273


def test_grade_has_color_for_each_letter() -> None:
    for ratio, expected_color in [
        (0.0, "bright_green"),  # A
        (0.10, "green"),        # B
        (0.20, "yellow"),       # C
        (0.30, "red"),          # D
        (0.50, "bright_red"),   # F
    ]:
        assert compute_grade(ratio).color == expected_color


def test_grade_f_has_no_modifier() -> None:
    g = compute_grade(0.7)
    assert g.letter == "F"
    assert g.modifier == ""
    assert g.display == "F"


def test_grade_display_concatenates_letter_and_modifier() -> None:
    g = compute_grade(0.03)  # A-
    assert g.display == g.letter + g.modifier
