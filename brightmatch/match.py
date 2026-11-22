"""Core contracts for matching brightness across video shots.

Data model
----------
* A frame is a 2-D ``list[list[float]]`` of RGB pixels:
  ``frame[row][channel]``, with channel order ``R, G, B``.
* A shot is a list of frames. Frames in one shot, and shots in one batch,
  are expected to share the same height and width.
* Every pixel sample and every luma value is linear light in ``[0.0, 1.0]``.
* Every gain is expressed in decibels (dB); ``20 dB`` is a 10x linear factor.
* Tests compare floating-point values with an absolute tolerance of ``1e-6``.
"""

from __future__ import annotations

import math

__all__ = [
    "BrightnessError",
    "shot_luma",
    "shot_stats",
    "match_gain",
    "apply_gain",
    "smooth_gains",
    "detect_outliers",
    "validate",
    "match_batch",
]

# Rec.709 luma weights for linear-light RGB.
_R_WEIGHT = 0.2126
_G_WEIGHT = 0.7152
_B_WEIGHT = 0.0722

# A pixel at or above this luma is treated as an overexposed/clipped sample.
_OVEREXPOSED_LUMA = 0.98

# Tolerance used at range boundaries during validation.
_EPS = 1e-6


class BrightnessError(ValueError):
    """Raised when brightness input or configuration violates a contract."""


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _pixel_luma(pixel: list[float]) -> float:
    r = _clamp01(pixel[0])
    g = _clamp01(pixel[1])
    b = _clamp01(pixel[2])
    return _R_WEIGHT * r + _G_WEIGHT * g + _B_WEIGHT * b


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Percentile with linear interpolation between order statistics."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (n - 1)
    low = int(math.floor(rank))
    high = min(low + 1, n - 1)
    frac = rank - low
    return sorted_values[low] * (1.0 - frac) + sorted_values[high] * frac


def shot_luma(frame: list[list[float]]) -> float:
    """Return the percentile-clipped mean Rec.709 luma of one frame."""
    if not frame:
        raise BrightnessError("frame is empty")

    lumas: list[float] = []
    for row in frame:
        if len(row) != 3:
            raise BrightnessError("frame row is not an RGB pixel")
        lumas.append(_pixel_luma(row))

    if len(lumas) < 2:
        return lumas[0]

    ordered = sorted(lumas)
    lo = _percentile(ordered, 5.0)
    hi = _percentile(ordered, 95.0)
    clipped = [min(hi, max(lo, value)) for value in lumas]
    return sum(clipped) / len(clipped)


def shot_stats(shot: list[list[list[float]]]) -> dict[str, float]:
    """Return robust luma statistics for one whole shot."""
    if not shot:
        return {}

    lumas: list[float] = []
    for frame in shot:
        for row in frame:
            if len(row) != 3:
                raise BrightnessError("frame row is not an RGB pixel")
            luma = _pixel_luma(row)
            if luma >= _OVEREXPOSED_LUMA:
                continue
            lumas.append(luma)

    if not lumas:
        raise BrightnessError("shot has no usable (non-overexposed) pixels")

    ordered = sorted(lumas)
    return {
        "mean": sum(lumas) / len(lumas),
        "p10": _percentile(ordered, 10.0),
        "p90": _percentile(ordered, 90.0),
    }


def match_gain(
    ref: list[list[list[float]]],
    cur: list[list[list[float]]],
    mode: str = "mean",
) -> float:
    """Return the gain in dB that makes ``cur`` match ``ref``."""
    if mode not in ("mean", "percentile"):
        raise BrightnessError(f"unknown mode: {mode!r}")

    ref_stats = shot_stats(ref)
    cur_stats = shot_stats(cur)
    if not ref_stats or not cur_stats:
        raise BrightnessError("cannot match gain for an empty shot")

    if mode == "mean":
        ref_level = ref_stats["mean"]
        cur_level = cur_stats["mean"]
    else:
        ref_level = 0.5 * (ref_stats["p10"] + ref_stats["p90"])
        cur_level = 0.5 * (cur_stats["p10"] + cur_stats["p90"])

    if ref_level <= 0.0 or cur_level <= 0.0:
        raise BrightnessError("cannot match gain for a non-positive level")

    return 20.0 * math.log10(ref_level / cur_level)


def apply_gain(frame: list[list[float]], db: float) -> list[list[float]]:
    """Apply a linear gain to every channel of ``frame`` and clamp to 0..1."""
    if not frame:
        return []

    factor = 10.0 ** (db / 20.0)
    return [[_clamp01(sample * factor) for sample in row] for row in frame]


def smooth_gains(gains: list[float], window: int) -> list[float]:
    """Smooth per-shot gains across neighbouring shots to avoid jumps."""
    if isinstance(window, bool) or not isinstance(window, int):
        raise BrightnessError("window must be an integer")
    if window <= 0:
        raise BrightnessError("window must be positive")
    if window % 2 == 0:
        raise BrightnessError("window must be odd")

    if not gains:
        return []

    half = window // 2
    n = len(gains)
    smoothed: list[float] = []
    for i in range(n):
        start = max(0, i - half)
        end = min(n, i + half + 1)
        segment = gains[start:end]
        smoothed.append(sum(segment) / len(segment))
    return smoothed


def detect_outliers(gains: list[float], max_db: float) -> list[int]:
    """Return indices of gain outliers relative to the batch median."""
    if not isinstance(max_db, (int, float)) or isinstance(max_db, bool):
        raise BrightnessError("max_db must be a number")
    if not math.isfinite(max_db) or max_db < 0.0:
        raise BrightnessError("max_db must be a non-negative finite threshold")

    if not gains:
        return []

    ordered = sorted(gains)
    n = len(ordered)
    if n % 2 == 1:
        median = ordered[n // 2]
    else:
        median = 0.5 * (ordered[n // 2 - 1] + ordered[n // 2])

    return [
        index
        for index, gain in enumerate(gains)
        if abs(gain - median) > max_db
    ]


def validate(shots: list[list[list[list[float]]]]) -> list[str]:
    """Return a list of human-readable problems, or ``[]`` when valid."""
    problems: list[str] = []

    if not shots:
        problems.append("batch contains no shots")
        return problems

    expected_rows: int | None = None

    for shot_index, shot in enumerate(shots):
        if not shot:
            problems.append(f"shot {shot_index} is empty")
            continue
        for frame_index, frame in enumerate(shot):
            where = f"shot {shot_index} frame {frame_index}"
            if not frame:
                problems.append(f"{where} is empty")
                continue
            if expected_rows is None:
                expected_rows = len(frame)
            elif len(frame) != expected_rows:
                problems.append(
                    f"{where} has {len(frame)} rows; expected {expected_rows}"
                )
            for row_index, row in enumerate(frame):
                pixel_where = f"{where} pixel {row_index}"
                if len(row) != 3:
                    problems.append(
                        f"{pixel_where} has {len(row)} channels; expected 3 (RGB)"
                    )
                    continue
                for channel, sample in enumerate(row):
                    sample_where = f"{pixel_where} channel {channel}"
                    if not isinstance(sample, (int, float)) or isinstance(
                        sample, bool
                    ):
                        problems.append(f"{sample_where} is not a number")
                        continue
                    if math.isnan(sample):
                        problems.append(f"{sample_where} is NaN")
                        continue
                    if math.isinf(sample):
                        problems.append(f"{sample_where} is infinite")
                        continue
                    if sample < -_EPS or sample > 1.0 + _EPS:
                        problems.append(
                            f"{sample_where}={sample} is outside [0.0, 1.0]"
                        )

    return problems


def match_batch(
    shots: list[list[list[list[float]]]],
    config: dict | None = None,
) -> dict:
    """Match every shot in a batch against a reference shot."""
    config = dict(config or {})

    mode = config.get("mode", "mean")
    if mode not in ("mean", "percentile"):
        raise BrightnessError(f"unknown mode: {mode!r}")

    window = config.get("window", 1)
    if isinstance(window, bool) or not isinstance(window, int):
        raise BrightnessError("window must be an integer")
    if window <= 0:
        raise BrightnessError("window must be positive")
    if window % 2 == 0:
        raise BrightnessError("window must be odd")

    max_db = config.get("max_db", 6.0)
    if not isinstance(max_db, (int, float)) or isinstance(max_db, bool):
        raise BrightnessError("max_db must be a number")
    if not math.isfinite(max_db) or max_db < 0.0:
        raise BrightnessError("max_db must be a non-negative finite threshold")

    problems = validate(shots)
    if problems:
        raise BrightnessError("invalid batch: " + "; ".join(problems))

    reference = config.get("reference", 0)
    if isinstance(reference, bool) or not isinstance(reference, int):
        raise BrightnessError("reference must be an integer shot index")
    if reference < 0 or reference >= len(shots):
        raise BrightnessError(f"reference index {reference} is out of range")

    ref_shot = shots[reference]
    gains = [match_gain(ref_shot, shot, mode) for shot in shots]
    smoothed = smooth_gains(gains, window)
    outliers = detect_outliers(gains, max_db)
    gained_shots = [
        [apply_gain(frame, smoothed[index]) for frame in shot]
        for index, shot in enumerate(shots)
    ]

    return {
        "gains": gains,
        "smoothed": smoothed,
        "outliers": outliers,
        "shots": gained_shots,
        "reference": reference,
    }
