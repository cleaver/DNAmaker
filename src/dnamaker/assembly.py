"""Deterministic Gibson product simulation from ordered, pre-overlapped fragments.

This predicts sequence from specified exact junctions; it does not design primers,
choose fragment order/orientation, or predict experimental assembly efficiency.
"""

from __future__ import annotations

import json

from .errors import BiologyError
from .models import Construct, Feature, Location
from .validation import validate_construct_data


def assemble_gibson(
    fragments: list[Construct],
    *,
    overlaps: list[int],
    name: str,
    circular: bool = True,
    min_overlap: int = 15,
) -> Construct:
    """Join each suffix to the next prefix; last overlap closes circular products.

    All inputs must be linear, unambiguous A/C/G/T, and already oriented.
    Base case is normalized before validation and matching; output is uppercase.
    Each fragment must contribute bases outside its incoming/outgoing overlaps.
    Overlap lengths are explicit so repeated ends cannot silently select a join.
    """
    if len(fragments) < 2 or not name.strip():
        raise BiologyError(
            "invalid_assembly", "Provide at least two fragments and a product name."
        )
    if type(min_overlap) is not int or min_overlap < 1:
        raise BiologyError("invalid_overlap", "min_overlap must be a positive integer.")
    expected = len(fragments) if circular else len(fragments) - 1
    if len(overlaps) != expected:
        raise BiologyError(
            "invalid_overlap",
            f"Provide exactly {expected} overlap lengths in junction order.",
        )
    # Assignment and model_copy updates can bypass Construct's initial validator.
    # Normalize only base case: preserve coordinates and the caller's objects.
    fragments = [
        fragment.model_copy(update={"sequence": fragment.sequence.upper()})
        for fragment in fragments
    ]
    for index, fragment in enumerate(fragments):
        valid, checks = validate_construct_data(fragment)
        if not valid or set(fragment.sequence) - set("ACGT"):
            raise BiologyError(
                "invalid_fragment",
                "Fragments must have valid annotations and unambiguous A/C/G/T sequence.",
                {"fragment": index, "checks": checks},
            )
        if fragment.topology != "linear":
            raise BiologyError(
                "fragment_not_linear",
                "Linearize each fragment before assembly.",
                {"fragment": index},
            )
    for index, length in enumerate(overlaps):
        left, right = fragments[index], fragments[(index + 1) % len(fragments)]
        if type(length) is not int or not min_overlap <= length < min(
            len(left.sequence), len(right.sequence)
        ):
            raise BiologyError(
                "invalid_overlap",
                "Overlap must meet min_overlap and be shorter than both fragments.",
                {"junction": index, "overlap": length},
            )
        if left.sequence[-length:] != right.sequence[:length]:
            raise BiologyError(
                "overlap_mismatch",
                "Fragment suffix does not exactly match the next prefix.",
                {
                    "junction": index,
                    "left": left.name,
                    "right": right.name,
                    "overlap": length,
                },
            )
    for index, fragment in enumerate(fragments):
        incoming = overlaps[index - 1] if index or circular else 0
        outgoing = overlaps[index] if index < len(overlaps) else 0
        if incoming + outgoing >= len(fragment.sequence):
            raise BiologyError(
                "overlapping_junctions",
                "Each fragment must contain sequence outside its junction overlaps.",
                {"fragment": index},
            )

    sequence = fragments[0].sequence
    offsets = [0]
    for index, fragment in enumerate(fragments[1:]):
        offsets.append(len(sequence) - overlaps[index])
        sequence += fragment.sequence[overlaps[index] :]
    if circular:
        sequence = sequence[: -overlaps[-1]]
    size = len(sequence)
    features = []
    for fragment, offset in zip(fragments, offsets):
        for feature in fragment.features:
            parts = []
            for part in feature.locations():
                start, end = part.start + offset, part.end + offset
                if end <= size:
                    mapped = [Location(start=start, end=end)]
                elif start >= size:
                    mapped = [Location(start=start - size, end=end - size)]
                else:
                    mapped = [
                        Location(start=start, end=size),
                        Location(start=0, end=end - size),
                    ]
                    if feature.strand == -1:
                        mapped.reverse()
                parts.extend(mapped)
            features.append(
                feature.model_copy(
                    deep=True,
                    update={
                        "start": min(p.start for p in parts),
                        "end": max(p.end for p in parts),
                        "parts": parts if len(parts) > 1 else None,
                    },
                )
            )
    # Retain source annotations and identify every checked junction in the product.
    for index, length in enumerate(overlaps):
        start = offsets[index + 1] if index + 1 < len(offsets) else 0
        features.append(
            Feature(
                name=f"Gibson junction {index + 1}",
                type="misc_feature",
                start=start,
                end=start + length,
                strand=1,
                qualifiers={
                    "note": [
                        f"Exact {length} bp overlap: {fragments[index].name} -> {fragments[(index + 1) % len(fragments)].name}"
                    ]
                },
            )
        )
    provenance = {
        "method": "Gibson exact-overlap simulation",
        "fragments": [f.name for f in fragments],
        "overlaps": overlaps,
        "circular": circular,
        "min_overlap": min_overlap,
    }
    product = Construct(
        name=name,
        sequence=sequence,
        topology="circular" if circular else "linear",
        features=features,
        metadata={"comment": json.dumps(provenance)},
    )
    valid, checks = validate_construct_data(product)
    if not valid:
        raise BiologyError(
            "invalid_assembly_product",
            "Assembled product failed structural validation.",
            {"checks": checks},
        )
    return product
