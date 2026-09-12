"""Feature location operations for construct mutations."""

from __future__ import annotations

from .models import Feature, Location


def feature_overlaps(feature: Feature, start: int, end: int) -> bool:
    return any(part.start < end and part.end > start for part in feature.locations())


def shift_feature(feature: Feature, delta: int) -> Feature:
    updates = {
        "start": feature.start + delta,
        "end": feature.end + delta,
    }
    if feature.parts:
        updates["parts"] = [
            Location(start=part.start + delta, end=part.end + delta)
            for part in feature.parts
        ]
    return feature.model_copy(update=updates)
