"""File-backed implementation of the shared BiologyService interface."""

from __future__ import annotations

import os
from itertools import pairwise
from pathlib import Path
from uuid import uuid4

from agent.models import ConstructRef, ConstructSummary, ValidationResult

from .errors import BiologyError
from .features import feature_overlaps, shift_feature
from .io import load_construct, require_format, write_construct
from .models import Construct, Feature
from .restriction import find_restriction_sites as scan_restriction_sites
from .sequence import normalize_dna
from .validation import validate_construct_data


class BiologyServiceAdapter:
    """Concrete adapter that keeps biology operations independent of SnapGene."""

    def __init__(
        self,
        workspace: str | Path | None = None,
        artifact_dir: str | Path | None = None,
    ):
        self.workspace = Path(workspace or Path.cwd()).resolve()
        configured_artifacts = (
            Path(artifact_dir)
            if artifact_dir
            else self.workspace / "artifacts" / "biology"
        )
        if not configured_artifacts.is_absolute():
            configured_artifacts = self.workspace / configured_artifacts
        self.artifact_dir = configured_artifacts.resolve()
        self._ensure_inside_workspace(self.artifact_dir)

    def read_construct(self, construct: ConstructRef) -> ConstructSummary:
        loaded, reference = self._load(construct)
        return ConstructSummary(
            construct=reference,
            sequence_length=len(loaded.sequence),
            topology=loaded.topology,
            features=[feature.summary() for feature in loaded.features],
        )

    def replace_region(
        self,
        construct: ConstructRef,
        *,
        target: str,
        replacement_sequence: str,
        replacement_name: str | None,
    ) -> ConstructRef:
        loaded, _ = self._load(construct)
        replacement = normalize_dna(replacement_sequence)
        matches = [
            index
            for index, feature in enumerate(loaded.features)
            if feature.name == target
        ]
        if not matches:
            raise BiologyError(
                "target_not_found",
                f"No feature named {target!r} was found.",
                {"target": target},
            )
        if len(matches) > 1:
            raise BiologyError(
                "target_ambiguous",
                f"Multiple features named {target!r} were found.",
                {"target": target, "matches": len(matches)},
            )

        target_index = matches[0]
        target_feature = loaded.features[target_index]
        target_locations = target_feature.locations()
        # Preserve strand order so origin-spanning joins remain unsupported.
        ordered_parts = (
            target_locations
            if target_feature.strand != -1
            else list(reversed(target_locations))
        )
        if any(left.end != right.start for left, right in pairwise(ordered_parts)):
            raise BiologyError(
                "unsupported_location",
                "Non-contiguous or origin-spanning target features are not supported by the MVP.",
                {"target": target},
            )
        # SnapGene can export one biological feature as adjacent joined
        # segments (for example EGFP in pEGFP-N1). Treat that representation as
        # the equivalent single interval for replacement, while continuing to
        # reject genuine gaps and origin-spanning locations.
        start = min(part.start for part in target_locations)
        end = max(part.end for part in target_locations)
        if not (0 <= start < end <= len(loaded.sequence)):
            raise BiologyError(
                "invalid_feature_location",
                "Target feature has an invalid location.",
                {"target": target, "start": start, "end": end},
            )

        for index, feature in enumerate(loaded.features):
            if (
                index != target_index
                and feature_overlaps(feature, start, end)
                and not _is_whole_construct_source(feature, len(loaded.sequence))
            ):
                raise BiologyError(
                    "overlapping_feature",
                    "Replacement would partially or completely remove another feature.",
                    {"target": target, "overlap": feature.name},
                )

        delta = len(replacement) - (end - start)
        new_sequence = loaded.sequence[:start] + replacement + loaded.sequence[end:]
        updated_features: list[Feature] = []
        for index, feature in enumerate(loaded.features):
            if index == target_index:
                if replacement_name is None:
                    continue
                qualifiers = {
                    key: list(values)
                    for key, values in feature.qualifiers.items()
                    if key
                    not in {
                        "label",
                        "gene",
                        "name",
                        "locus_tag",
                        "translation",
                        "product",
                        "note",
                        "protein_id",
                        "db_xref",
                        "codon_start",
                        "transl_table",
                        "transl_except",
                        "function",
                        "experiment",
                        "inference",
                    }
                }
                qualifiers["label"] = [replacement_name]
                updated_features.append(
                    feature.model_copy(
                        update={
                            "name": replacement_name,
                            "start": start,
                            "end": start + len(replacement),
                            "parts": None,
                            "qualifiers": qualifiers,
                        }
                    )
                )
            elif _is_whole_construct_source(feature, len(loaded.sequence)):
                updated_features.append(
                    feature.model_copy(
                        update={"start": 0, "end": len(new_sequence), "parts": None}
                    )
                )
            elif feature.start >= end:
                updated_features.append(shift_feature(feature, delta))
            else:
                updated_features.append(feature)

        modified = loaded.model_copy(
            update={
                "sequence": new_sequence,
                "features": updated_features,
            }
        )
        return self._write_mutation(modified, "replace")

    def gibson_assemble(
        self, fragments: list[ConstructRef], *, overlaps: list[int], name: str,
        circular: bool = True, min_overlap: int = 15,
    ) -> ConstructRef:
        from .assembly import assemble_gibson

        loaded = [self._load(reference)[0] for reference in fragments]
        product = assemble_gibson(loaded, overlaps=overlaps, name=name,
                                  circular=circular, min_overlap=min_overlap)
        return self._write_mutation(product, "gibson")

    def add_annotation(
        self,
        construct: ConstructRef,
        *,
        name: str,
        feature_type: str,
        start: int,
        end: int,
        strand: int,
    ) -> ConstructRef:
        loaded, _ = self._load(construct)
        if not name.strip() or not feature_type.strip():
            raise BiologyError(
                "invalid_annotation", "Annotation name and feature type are required."
            )
        if not (0 <= start < end <= len(loaded.sequence)):
            raise BiologyError(
                "invalid_feature_location",
                "Annotation location is outside the construct.",
                {"start": start, "end": end, "sequence_length": len(loaded.sequence)},
            )
        if strand not in {1, -1}:
            raise BiologyError(
                "invalid_strand",
                "Annotation strand must be 1 or -1.",
                {"strand": strand},
            )
        annotation = Feature(
            name=name,
            type=feature_type,
            start=start,
            end=end,
            strand=strand,
            qualifiers={"label": [name]},
        )
        modified = loaded.model_copy(
            update={"features": [*loaded.features, annotation]}
        )
        return self._write_mutation(modified, "annotate")

    def find_restriction_sites(
        self, construct: ConstructRef, *, enzyme: str
    ) -> list[dict]:
        loaded, _ = self._load(construct)
        return scan_restriction_sites(loaded.sequence, enzyme, topology=loaded.topology)

    def validate_construct(self, construct: ConstructRef) -> ValidationResult:
        loaded, _ = self._load(construct)
        valid, checks = validate_construct_data(loaded)
        return ValidationResult(valid=valid, checks=checks)

    def save_construct(
        self, construct: ConstructRef, *, output_path: str, output_format: str
    ) -> ConstructRef:
        loaded, _ = self._load(construct)
        format = require_format(output_format, output=True)
        destination = self._resolve_path(output_path)
        write_construct(loaded, destination, format)
        return self._reference(destination, format, loaded.name)

    def _load(self, reference: ConstructRef) -> tuple[Construct, ConstructRef]:
        if reference.format == "snapgene":
            raise BiologyError(
                "unsupported_format",
                "SnapGene artifacts must be converted before biology operations.",
                {"format": reference.format},
            )
        format = require_format(reference.format)
        path = self._resolve_path(reference.path)
        loaded = load_construct(path, format, name=reference.name)
        return loaded, self._reference(path, format, loaded.name)

    def _write_mutation(self, construct: Construct, operation: str) -> ConstructRef:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        destination = self.artifact_dir / f"{operation}-{uuid4().hex}.gb"
        write_construct(construct, destination, "genbank")
        return self._reference(destination, "genbank", construct.name)

    def _resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        resolved = (path if path.is_absolute() else self.workspace / path).resolve()
        return self._ensure_inside_workspace(resolved)

    def _ensure_inside_workspace(self, path: Path) -> Path:
        try:
            path.relative_to(self.workspace)
        except ValueError as error:
            raise BiologyError(
                "path_outside_workspace",
                "Artifact path must remain inside the biology workspace.",
                {"path": str(path), "workspace": str(self.workspace)},
            ) from error
        return path

    def _reference(self, path: Path, format: str, name: str | None) -> ConstructRef:
        return ConstructRef(
            path=path.relative_to(self.workspace).as_posix(), format=format, name=name
        )


def create_biology_adapter() -> BiologyServiceAdapter:
    """Factory loaded by ``agent.bootstrap`` through an environment variable."""
    return BiologyServiceAdapter(
        workspace=os.environ.get("DNA_MAKER_WORKSPACE"),
        artifact_dir=os.environ.get("DNA_MAKER_BIOLOGY_ARTIFACT_DIR"),
    )


def _is_whole_construct_source(feature: Feature, sequence_length: int) -> bool:
    return (
        feature.type == "source"
        and feature.parts is None
        and feature.start == 0
        and feature.end == sequence_length
    )
