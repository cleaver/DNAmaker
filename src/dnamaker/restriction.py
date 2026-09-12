"""Restriction recognition-site scanning."""

from __future__ import annotations

from Bio import Restriction

from .errors import BiologyError
from .sequence import IUPAC_DNA, normalize_dna, reverse_complement

IUPAC_BASES = {
    "A": frozenset("A"),
    "C": frozenset("C"),
    "G": frozenset("G"),
    "T": frozenset("T"),
    "R": frozenset("AG"),
    "Y": frozenset("CT"),
    "S": frozenset("GC"),
    "W": frozenset("AT"),
    "K": frozenset("GT"),
    "M": frozenset("AC"),
    "B": frozenset("CGT"),
    "D": frozenset("AGT"),
    "H": frozenset("ACT"),
    "V": frozenset("ACG"),
    "N": IUPAC_DNA,
}


def find_restriction_sites(
    sequence: str, enzyme_name: str, *, topology: str
) -> list[dict[str, int | str]]:
    sequence = normalize_dna(sequence)
    enzyme = _resolve_enzyme(enzyme_name)
    recognition = str(enzyme.site).upper()
    size = len(recognition)
    if size == 0 or len(sequence) < size:
        return []

    patterns: list[tuple[str, int]] = [(recognition, 1)]
    reverse_pattern = reverse_complement(recognition)
    if reverse_pattern != recognition:
        patterns.append((reverse_pattern, -1))

    circular = topology == "circular"
    limit = len(sequence) if circular else len(sequence) - size + 1
    scan_sequence = sequence + sequence[: size - 1] if circular else sequence
    results: list[dict[str, int | str]] = []
    seen: set[tuple[int, int]] = set()
    for position in range(limit):
        window = scan_sequence[position : position + size]
        for pattern, strand in patterns:
            if (position, strand) in seen:
                continue
            if _matches(window, pattern):
                results.append(
                    {"position": position, "strand": strand, "site": recognition}
                )
                seen.add((position, strand))
    return sorted(
        results, key=lambda site: (int(site["position"]), int(site["strand"]))
    )


def _resolve_enzyme(enzyme_name: str):
    enzyme = getattr(Restriction, enzyme_name, None)
    if enzyme is None or not hasattr(enzyme, "site"):
        raise BiologyError(
            "unknown_enzyme",
            f"Unknown restriction enzyme: {enzyme_name}.",
            {"enzyme": enzyme_name},
        )
    return enzyme


def _matches(sequence: str, pattern: str) -> bool:
    return len(sequence) == len(pattern) and all(
        bool(
            IUPAC_BASES.get(actual, frozenset())
            & IUPAC_BASES.get(expected, frozenset())
        )
        for actual, expected in zip(sequence, pattern)
    )
