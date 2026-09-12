"""Prepare the real-fixture GenBank demo: uv run python -m dnamaker.handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from Bio import SeqIO

from agent.models import ConstructRef
from agent.session import WorkflowManager
from dnamaker.service import BiologyServiceAdapter


def prepare_handoff(workspace: Path) -> dict:
    """Replace the complete EGFP CDS with the fixture's mCherry CDS.

    This is a sequence replacement demo, not a Gibson assembly simulation.
    The saved file is reloaded and validated so its exact ref is ready for
    conversion in the receiving workflow.
    """
    workspace = workspace.resolve()
    run = f"artifacts/biology/handoff-{uuid4().hex}"
    biology = BiologyServiceAdapter(workspace, run)
    # No SnapGene operations are performed while preparing the handoff.
    manager = WorkflowManager(biology, None)  # type: ignore[arg-type]
    sources = ["inputs/pEGFP-N1.gb", "inputs/mCherry.gb"]
    hashes = {
        path: hashlib.sha256((workspace / path).read_bytes()).hexdigest()
        for path in sources
    }
    for path in sources:
        validation = biology.validate_construct(ConstructRef(path))
        if not validation.valid:
            raise ValueError(f"Invalid input {path}: {validation.checks}")

    donor = SeqIO.read(workspace / sources[1], "genbank")
    matches = [
        f
        for f in donor.features
        if f.type == "CDS" and f.qualifiers.get("label") == ["mCherry"]
    ]
    if len(matches) != 1:
        raise ValueError("Expected exactly one mCherry CDS in the donor")
    replacement = matches[0].extract(donor.seq)
    # Fixture-specific CDS checks: start, stop, frame, internal stops, protein.
    protein = str(replacement.translate(cds=True))
    if protein != matches[0].qualifiers["translation"][0]:
        raise ValueError("Donor CDS disagrees with its annotated translation")

    workflow = manager.start(
        "Replace complete EGFP CDS with fixture mCherry CDS; preserve CMV promoter"
    )
    summary = manager.read_construct(
        workflow.id, ConstructRef(sources[0], name="pEGFP-N1-mCherry")
    )
    target = [
        f for f in summary["features"] if f["name"] == "EGFP" and f["type"] == "CDS"
    ]
    if len(target) != 1 or target[0]["strand"] != 1:
        raise ValueError("Expected exactly one forward EGFP CDS")
    manager.replace_region(
        workflow.id,
        target="EGFP",
        replacement_sequence=str(replacement),
        replacement_name="mCherry",
    )
    sites = manager.find_restriction_sites(workflow.id, enzyme="EcoRI")
    if not manager.validate_construct(workflow.id)["valid"]:
        raise ValueError("Edited construct failed validation")
    saved = manager.save_construct(
        workflow.id, output_path=f"{run}/pEGFP-N1-mCherry.gb", output_format="genbank"
    )
    ref = ConstructRef(**saved["construct"])
    manager.read_construct(workflow.id, ref)
    validation = manager.validate_construct(workflow.id)
    if not validation["valid"]:
        raise ValueError("Saved construct failed validation")
    for path, digest in hashes.items():
        if hashlib.sha256((workspace / path).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Input changed: {path}")
    report = {
        "construct": ref.to_dict(),
        "validation": validation,
        "input_sha256": hashes,
        "output_sha256": hashlib.sha256(
            (workspace / ref.path).read_bytes()
        ).hexdigest(),
        "sequence_length": biology.read_construct(ref).sequence_length,
        "replacement_cds_translation_matches_donor": True,
        "restriction_sites": sites["sites"],
        "enzyme": "EcoRI",
        "workflow": workflow.to_dict(),
        "snapgene_conversion": "pending on Windows",
    }
    (workspace / run / "handoff.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(prepare_handoff(args.workspace), indent=2))


if __name__ == "__main__":
    main()
