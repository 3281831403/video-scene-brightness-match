"""Brightness matching primitives for multi-camera video editing."""

from .match import (
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

__all__ = [
    "BrightnessError",
    "apply_gain",
    "detect_outliers",
    "match_batch",
    "match_gain",
    "shot_luma",
    "shot_stats",
    "smooth_gains",
    "validate",
]
