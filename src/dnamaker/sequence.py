"""Small sequence helpers shared by the biology implementation."""

from __future__ import annotations

from Bio.Seq import Seq

from .errors import BiologyError

IUPAC_DNA = frozenset("ACGTRYSWKMBDHVN")


def normalize_dna(sequence: str, *, allow_empty: bool = False) -> str:
    if not isinstance(sequence, str):
        raise BiologyError("invalid_sequence", "DNA sequence must be a string.")
    normalized = "".join(sequence.split()).upper()
    if not normalized and not allow_empty:
        raise BiologyError("invalid_sequence", "DNA sequence must not be empty.")
    invalid = sorted(set(normalized) - IUPAC_DNA)
    if invalid:
        raise BiologyError(
            "invalid_sequence",
            "DNA sequence contains unsupported symbols.",
            {"invalid_symbols": invalid},
        )
    return normalized


def reverse_complement(sequence: str) -> str:
    return str(Seq(normalize_dna(sequence)).reverse_complement())


def translate(sequence: str, *, frame: int = 0, to_stop: bool = False) -> str:
    if frame not in (0, 1, 2):
        raise BiologyError(
            "invalid_frame", "Translation frame must be 0, 1, or 2.", {"frame": frame}
        )
    normalized = normalize_dna(sequence)
    return str(Seq(normalized[frame:]).translate(to_stop=to_stop))
