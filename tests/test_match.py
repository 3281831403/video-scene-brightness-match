"""Executable specification for the brightness-matching stubs.

There are exactly 15 tests: one per documented defect plus five contract
checks. Every test calls at least one public stub in ``brightmatch.match``.
"""

import math

import pytest

from brightmatch.match import (
    BrightnessError,
    apply_gain,
    detect_outliers,
    match_batch,
    match_gain,
    shot_luma,
    shot_stats,
    smooth_gains,
    validate,
)


def test_shot_luma_uses_rec709_green_weight():
    """Defect 1: luma must not use an equal-weight RGB average."""
    frame = [[0.0, 1.0, 0.0]]

    assert shot_luma(frame) == pytest.approx(0.7152, abs=1e-6)


def test_shot_stats_ignores_overexposed_pixels():
    """Defect 2: clipped highlights must not lift a dark shot's statistics."""
    shot = [[[0.10, 0.10, 0.10]] for _ in range(9)]
    shot.append([[1.0, 1.0, 1.0]])

    stats = shot_stats(shot)

    assert stats["mean"] == pytest.approx(0.10, abs=1e-6)
    assert stats["p10"] == pytest.approx(0.10, abs=1e-6)
    assert stats["p90"] == pytest.approx(0.10, abs=1e-6)


def test_match_gain_returns_decibels():
    """Defect 3: gain must be a dB value, not the linear ratio 0.5."""
    ref = [[[0.10, 0.10, 0.10]]]
    cur = [[[0.20, 0.20, 0.20]]]

    expected_db = 20.0 * math.log10(0.10 / 0.20)

    assert match_gain(ref, cur, "mean") == pytest.approx(expected_db, abs=1e-6)


def test_apply_gain_clamps_highlights():
    """Defect 4: a positive gain must clamp at white, never wrap to black."""
    frame = [[0.80, 0.90, 1.00]]

    gained = apply_gain(frame, 6.0)

    assert gained[0][0] == pytest.approx(1.0, abs=1e-6)
    assert gained[0][1] == pytest.approx(1.0, abs=1e-6)
    assert gained[0][2] == pytest.approx(1.0, abs=1e-6)


def test_smooth_gains_zero_window_raises():
    """Defect 5: a zero-sized window must not reach a divide-by-zero path."""
    with pytest.raises(BrightnessError):
        smooth_gains([0.0, 3.0, 6.0], 0)


def test_detect_outliers_uses_content_and_max_db():
    """Defect 6: outlier detection must use max_db, not a fixed 6 dB rule."""
    gains = [0.0, 0.5, 1.0, 8.0]

    assert detect_outliers(gains, 12.0) == []
    assert detect_outliers(gains, 3.0) == [3]


def test_validate_rejects_inconsistent_dimensions():
    """Defect 7: mismatched frame sizes must be reported before indexing."""
    shots = [
        [[[0.10, 0.10, 0.10]]],
        [[[0.10, 0.10, 0.10], [0.10, 0.10, 0.10]]],
    ]

    problems = validate(shots)

    assert problems


def test_validate_rejects_nan():
    """Defect 8: NaN samples must be rejected instead of blackening a shot."""
    shots = [[[[float("nan"), 0.20, 0.20]]]]

    problems = validate(shots)

    assert problems
    assert any("nan" in problem.lower() for problem in problems)


def test_match_batch_isolates_per_shot_statistics():
    """Defect 9: every shot must get its own measurement, not a shared one."""
    ref = [[[0.20, 0.20, 0.20]]]
    shots = [
        ref,
        [[[0.40, 0.40, 0.40]]],
        [[[0.10, 0.10, 0.10]]],
    ]

    result = match_batch(shots, {"mode": "mean", "window": 1, "max_db": 12.0})

    assert result["gains"][0] == pytest.approx(0.0, abs=1e-6)
    assert result["gains"][1] == pytest.approx(20.0 * math.log10(0.5), abs=1e-6)
    assert result["gains"][2] == pytest.approx(20.0 * math.log10(2.0), abs=1e-6)


def test_match_batch_rejects_negative_window():
    """Defect 10: batch configuration must reject a negative window."""
    shots = [[[[0.10, 0.10, 0.10]]]]

    with pytest.raises(BrightnessError):
        match_batch(shots, {"mode": "mean", "window": -1, "max_db": 6.0})


def test_identical_shot_gain_is_zero_db():
    """Extra: matching a shot against itself is 0 dB within 1e-6."""
    shot = [[[0.12, 0.34, 0.56]]]

    assert match_gain(shot, shot, "mean") == pytest.approx(0.0, abs=1e-6)


def test_apply_gain_zero_db_is_identity():
    """Extra: 0 dB leaves every sample and the frame shape unchanged."""
    frame = [[0.0, 0.5, 1.0]]

    assert apply_gain(frame, 0.0) == frame


def test_empty_shot_returns_empty_stats():
    """Extra: an empty shot yields an empty statistics mapping."""
    assert shot_stats([]) == {}


def test_smooth_gains_negative_window_raises():
    """Extra: smooth_gains itself rejects window < 0 with BrightnessError."""
    with pytest.raises(BrightnessError):
        smooth_gains([1.0, 2.0], -1)


def test_match_batch_preserves_order_on_success():
    """Extra: a successful batch returns shots and gains in input order."""
    shots = [
        [[[0.10, 0.10, 0.10]]],
        [[[0.20, 0.20, 0.20]]],
        [[[0.30, 0.30, 0.30]]],
    ]

    result = match_batch(shots, {"mode": "mean", "window": 1, "max_db": 12.0})

    assert len(result["shots"]) == 3
    assert result["gains"] == pytest.approx(
        [0.0, 20.0 * math.log10(0.5), 20.0 * math.log10(1.0 / 3.0)],
        abs=1e-6,
    )
    assert result["reference"] == 0
