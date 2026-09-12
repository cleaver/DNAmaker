"""Run the real Person 1 integration check with an annotated GenBank fixture.

Usage: python -m snapgene.vertical_slice
Requires the installed project dependencies and a closed, activated SnapGene.
Creates a unique artifact directory, retains a JSON workflow log, and opens last.
This checks annotation mutation and artifact interchange, not Gibson assembly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from Bio import SeqIO

from agent.bootstrap import manager_from_environment
from agent.errors import WorkflowError
from agent.models import ConstructRef


def require(condition: bool, message: str):
    if not condition:
        raise WorkflowError("vertical_slice_verification_failed", message)


def signature(record):
    return sorted(
        (
            feature.type,
            str(feature.location),
            tuple(feature.qualifiers.get("label", [])),
        )
        for feature in record.features
    )


def run(*, open_result: bool = True) -> dict:
    root = Path(os.environ.get("DNA_MAKER_WORKSPACE", Path.cwd())).resolve()
    os.environ.setdefault("DNA_MAKER_WORKSPACE", str(root))
    os.environ.setdefault(
        "DNA_MAKER_BIOLOGY_ADAPTER", "dnamaker.service:create_biology_adapter"
    )
    os.environ.setdefault(
        "DNA_MAKER_SNAPGENE_ADAPTER", "snapgene.adapter:create_service"
    )
    manager = manager_from_environment()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    run_dir = root / "artifacts" / f"vertical-slice-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    relative = run_dir.relative_to(root).as_posix()
    stem = f"pEGFP-N1-annotated-{stamp}"
    source = ConstructRef("inputs/pEGFP-N1.gb", "genbank")
    source_hash = hashlib.sha256((root / source.path).read_bytes()).hexdigest()
    original = SeqIO.read(root / source.path, "genbank")
    session = manager.start(
        "Add an MVP verification annotation to pEGFP-N1, validate, save GenBank, convert, render and open in SnapGene."
    )
    report = {
        "status": "running",
        "workflow_id": session.id,
        "input": source.to_dict(),
        "input_sha256": source_hash,
        "modification": "annotation only; sequence unchanged",
        "artifact_directory": relative,
    }
    try:
        manager.read_construct(session.id, source)
        label = "MVP integration verified"
        manager.add_annotation(
            session.id,
            name=label,
            feature_type="misc_feature",
            start=590,
            end=671,
            strand=1,
        )
        validation = manager.validate_construct(session.id)
        require(
            validation["valid"], "Biology validation rejected the modified construct."
        )
        saved = manager.save_construct(
            session.id, output_path=f"{relative}/{stem}.gb", output_format="genbank"
        )
        saved_ref = ConstructRef(**saved["construct"])
        record = SeqIO.read(root / saved_ref.path, "genbank")
        require(
            str(record.seq) == str(original.seq),
            "Annotation unexpectedly changed the sequence.",
        )
        require(
            len(record.features) == len(original.features) + 1,
            "Expected exactly one added annotation.",
        )
        added = [f for f in record.features if f.qualifiers.get("label") == [label]]
        require(
            len(added) == 1
            and int(added[0].location.start) == 590
            and int(added[0].location.end) == 671
            and added[0].location.strand == 1,
            "Added annotation has incorrect coordinates or orientation.",
        )
        # save_construct returns a reference without updating current_construct.
        # Reload and validate the exact saved artifact before converting it.
        manager.read_construct(session.id, saved_ref)
        saved_validation = manager.validate_construct(session.id)
        require(saved_validation["valid"], "Saved GenBank failed validation.")
        converted = manager.snapgene_convert(
            session.id, output_path=f"{relative}/{stem}.dna"
        )
        dna_ref = ConstructRef(**converted["construct"])
        rendered = manager.snapgene_render(
            session.id, output_path=f"{relative}/{stem}.png"
        )

        # Independent format QA before opening (CLI export requires a closed GUI).
        exported = manager.snapgene.export(
            dna_ref, output_path=f"{relative}/roundtrip-check.gb"
        )
        roundtrip = SeqIO.read(root / exported.path, "genbank")
        require(
            str(roundtrip.seq) == str(record.seq),
            "SnapGene conversion changed the sequence.",
        )
        require(
            roundtrip.annotations.get("topology") == record.annotations.get("topology"),
            "Topology changed.",
        )
        require(
            signature(roundtrip) == signature(record),
            "Feature types, locations, or labels changed in SnapGene.",
        )
        with (root / rendered["map_path"]).open("rb") as png:
            header = png.read(24)
        require(header[:8] == b"\x89PNG\r\n\x1a\n", "Map is not a PNG.")
        width, height = struct.unpack(">II", header[16:24])
        require(width > 100 and height > 100, "Map dimensions are unexpectedly small.")
        require(
            source_hash
            == hashlib.sha256((root / source.path).read_bytes()).hexdigest(),
            "Original fixture changed.",
        )
        report.update(
            {
                "genbank": saved_ref.to_dict(),
                "snapgene": dna_ref.to_dict(),
                "map_path": rendered["map_path"],
                "roundtrip_check": exported.to_dict(),
                "validation": saved_validation,
                "sequence_length": len(record.seq),
                "feature_count": len(record.features),
                "map_dimensions": [width, height],
                "sequence_preserved": True,
                "feature_locations_and_labels_preserved": True,
                "original_unchanged": True,
            }
        )
        if open_result:
            manager.snapgene_open(session.id)
        report.update({"status": "passed", "opened": open_result})
        return report
    except Exception as error:
        report.update({"status": "failed", "error": str(error)})
        raise
    finally:
        (run_dir / "workflow_status.json").write_text(
            json.dumps(session.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
        (run_dir / "verification.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Verify artifacts without opening the desktop app",
    )
    arguments = parser.parse_args()
    run(open_result=not arguments.no_open)
