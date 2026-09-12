"""Construct validation checks returned through the shared adapter."""

from __future__ import annotations

from .models import Construct
from .sequence import IUPAC_DNA


def validate_construct_data(construct: Construct) -> tuple[bool, list[dict]]:
    invalid_symbols = sorted(set(construct.sequence) - IUPAC_DNA)
    sequence_passed = bool(construct.sequence) and not invalid_symbols
    checks = [
        {
            "name": "sequence_alphabet",
            "passed": sequence_passed,
            "details": {"invalid_symbols": invalid_symbols},
        },
        {
            "name": "topology",
            "passed": construct.topology in {"linear", "circular"},
            "details": {"topology": construct.topology},
        },
    ]

    invalid_bounds = []
    for feature in construct.features:
        for part in feature.locations():
            if not (0 <= part.start < part.end <= len(construct.sequence)):
                invalid_bounds.append(
                    {"feature": feature.name, "start": part.start, "end": part.end}
                )
    checks.append(
        {
            "name": "feature_bounds",
            "passed": not invalid_bounds,
            "details": {"invalid_features": invalid_bounds},
        }
    )

    invalid_strands = [
        {"feature": feature.name, "strand": feature.strand}
        for feature in construct.features
        if feature.strand not in {1, -1}
    ]
    checks.append(
        {
            "name": "feature_strands",
            "passed": not invalid_strands,
            "details": {"invalid_features": invalid_strands},
        }
    )
    return all(check["passed"] for check in checks), checks
