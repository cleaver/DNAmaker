"""GenBank, FASTA, and structured JSON conversion."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import CompoundLocation, FeatureLocation, SeqFeature
from Bio.SeqRecord import SeqRecord

from .errors import BiologyError
from .models import Construct, Feature, Location

SUPPORTED_INPUT_FORMATS = frozenset({"genbank", "fasta", "json"})
SUPPORTED_OUTPUT_FORMATS = frozenset({"genbank", "fasta", "json"})
JSON_SCHEMA_VERSION = 1


def require_format(value: str, *, output: bool = False) -> str:
    allowed = SUPPORTED_OUTPUT_FORMATS if output else SUPPORTED_INPUT_FORMATS
    if value not in allowed:
        raise BiologyError(
            "unsupported_format",
            f"Unsupported {'output' if output else 'input'} format: {value!r}.",
            {"format": value, "allowed": sorted(allowed)},
        )
    return value


def load_construct(path: Path, format: str, *, name: str | None = None) -> Construct:
    if format == "snapgene":
        raise BiologyError(
            "unsupported_format",
            "SnapGene artifacts must be converted by the SnapGene adapter first.",
            {"format": format},
        )
    require_format(format)
    try:
        if format == "json":
            return _load_json(path, name=name)
        record = SeqIO.read(str(path), "genbank" if format == "genbank" else "fasta")
        return _construct_from_record(record, name=name)
    except BiologyError:
        raise
    except FileNotFoundError as error:
        raise BiologyError(
            "artifact_not_found",
            f"Construct artifact not found: {path}.",
            {"path": str(path)},
        ) from error
    except Exception as error:
        raise BiologyError(
            "parse_error",
            f"Could not parse construct artifact: {path}.",
            {"path": str(path), "format": format, "reason": str(error)},
        ) from error


def write_construct(construct: Construct, path: Path, format: str) -> None:
    require_format(format, output=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if format == "json":
            payload = {
                "schema_version": JSON_SCHEMA_VERSION,
                **construct.model_dump(mode="json"),
            }
            path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            return

        record = _record_from_construct(construct)
        if format == "fasta":
            record.features = []
        SeqIO.write(record, str(path), "genbank" if format == "genbank" else "fasta")
    except BiologyError:
        raise
    except Exception as error:
        raise BiologyError(
            "write_error",
            f"Could not write construct artifact: {path}.",
            {"path": str(path), "format": format, "reason": str(error)},
        ) from error


def _load_json(path: Path, *, name: str | None) -> Construct:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise BiologyError(
            "artifact_not_found",
            f"Construct artifact not found: {path}.",
            {"path": str(path)},
        ) from error
    except json.JSONDecodeError as error:
        raise BiologyError(
            "parse_error",
            f"Could not parse JSON construct: {path}.",
            {"reason": str(error)},
        ) from error
    if payload.get("schema_version") != JSON_SCHEMA_VERSION:
        raise BiologyError(
            "unsupported_schema",
            "Unsupported construct JSON schema version.",
            {
                "schema_version": payload.get("schema_version"),
                "supported": [JSON_SCHEMA_VERSION],
            },
        )
    payload = dict(payload)
    payload.pop("schema_version", None)
    try:
        construct = Construct.model_validate(payload)
    except Exception as error:
        raise BiologyError(
            "invalid_construct",
            "Construct JSON does not match the schema.",
            {"reason": str(error)},
        ) from error
    return construct.model_copy(update={"name": name}) if name else construct


def _construct_from_record(record: SeqRecord, *, name: str | None) -> Construct:
    construct_name = name or _record_name(record)
    topology = record.annotations.get("topology", "linear")
    if not isinstance(topology, str):
        topology = str(topology)
    features = []
    for index, raw_feature in enumerate(record.features):
        if raw_feature.location is None:
            raise BiologyError(
                "unsupported_location",
                "Construct feature has no concrete location.",
                {"feature_index": index, "feature_type": raw_feature.type},
            )
        parts = [
            Location(start=int(part.start), end=int(part.end))
            for part in raw_feature.location.parts
        ]
        qualifiers = _normalize_qualifiers(raw_feature.qualifiers)
        features.append(
            Feature(
                name=_feature_name(raw_feature.type, qualifiers, index),
                type=raw_feature.type,
                start=int(raw_feature.location.start),
                end=int(raw_feature.location.end),
                strand=raw_feature.location.strand,
                qualifiers=qualifiers,
                parts=parts if len(parts) > 1 else None,
            )
        )
    metadata = _json_safe(record.annotations)
    metadata["description"] = record.description
    return Construct(
        name=construct_name,
        sequence=str(record.seq).upper(),
        topology=topology,
        features=features,
        metadata=metadata,
    )


def _record_from_construct(construct: Construct) -> SeqRecord:
    if construct.topology not in {"linear", "circular"}:
        raise BiologyError(
            "invalid_topology",
            "Construct topology must be linear or circular.",
            {"topology": construct.topology},
        )
    record_id = re.sub(r"\s+", "_", construct.name).strip("_") or "construct"
    record = SeqRecord(
        Seq(construct.sequence),
        id=record_id,
        name=record_id,
        description=str(construct.metadata.get("description", construct.name)),
    )
    record.annotations = {
        str(key): value
        for key, value in construct.metadata.items()
        if key not in {"description", "molecule_type", "topology"}
    }
    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = construct.topology
    for feature in construct.features:
        location_parts = feature.locations()
        locations = [
            FeatureLocation(part.start, part.end, strand=feature.strand)
            for part in location_parts
        ]
        location = (
            locations[0]
            if len(locations) == 1
            else CompoundLocation(locations, operator="join")
        )
        qualifiers = {key: list(values) for key, values in feature.qualifiers.items()}
        qualifiers.setdefault("label", [feature.name])
        record.features.append(
            SeqFeature(location=location, type=feature.type, qualifiers=qualifiers)
        )
    return record


def _record_name(record: SeqRecord) -> str:
    candidate = record.name or record.id
    return candidate if candidate and candidate != "<unknown name>" else "construct"


def _feature_name(
    feature_type: str, qualifiers: dict[str, list[str]], index: int
) -> str:
    for key in ("label", "gene", "locus_tag", "name", "product", "note"):
        values = qualifiers.get(key)
        if values and values[0].strip():
            return values[0].strip()
    return f"{feature_type or 'feature'}_{index}"


def _normalize_qualifiers(qualifiers: dict[str, Any]) -> dict[str, list[str]]:
    return {
        str(key): [str(item) for item in values]
        if isinstance(values, (list, tuple))
        else [str(values)]
        for key, values in qualifiers.items()
    }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)
