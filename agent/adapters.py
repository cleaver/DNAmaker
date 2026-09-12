"""Contracts implemented by the Biology and SnapGene component owners."""

from __future__ import annotations

from typing import Protocol

from .models import ConstructRef, ConstructSummary, ValidationResult


class BiologyService(Protocol):
    def read_construct(self, construct: ConstructRef) -> ConstructSummary: ...

    def replace_region(
        self, construct: ConstructRef, *, target: str, replacement_sequence: str, replacement_name: str | None
    ) -> ConstructRef: ...

    def add_annotation(
        self, construct: ConstructRef, *, name: str, feature_type: str, start: int, end: int, strand: int
    ) -> ConstructRef: ...

    def find_restriction_sites(self, construct: ConstructRef, *, enzyme: str) -> list[dict]: ...

    def validate_construct(self, construct: ConstructRef) -> ValidationResult: ...

    def save_construct(self, construct: ConstructRef, *, output_path: str, output_format: str) -> ConstructRef: ...


class SnapGeneService(Protocol):
    def convert(self, construct: ConstructRef, *, output_path: str) -> ConstructRef: ...

    def render_map(self, construct: ConstructRef, *, output_path: str, size: int = 1200) -> str: ...

    def open(self, construct: ConstructRef) -> None: ...
