"""Run a self-contained, synthetic Gibson presentation demo without SnapGene.

uv run python -m dnamaker.gibson_demo
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from agent.bootstrap import UnavailableSnapGene
from agent.errors import WorkflowError
from agent.models import ConstructRef
from agent.session import WorkflowManager

from .io import load_construct, write_construct
from .models import Construct, Feature
from .service import BiologyServiceAdapter


def main() -> None:
    workspace = Path.cwd()
    run = (
        Path("artifacts")
        / f"gibson-demo-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"
    )
    left = "ACGTCAGTACGATCGTAGCA"
    right = "TGCACTGATCGATGCTACGT"
    backbone = "GATTACA" * 10
    insert = "CCGTA" * 10
    fragments = [
        Construct(
            name="synthetic_vector",
            sequence=left + backbone + right,
            features=[
                Feature(
                    name="Synthetic backbone", type="misc_feature", start=20, end=90
                )
            ],
        ),
        Construct(
            name="synthetic_insert",
            sequence=right + insert + left,
            features=[
                Feature(name="Synthetic insert", type="misc_feature", start=20, end=70)
            ],
        ),
    ]
    refs = []
    for fragment in fragments:
        path = run / f"{fragment.name}.gb"
        write_construct(fragment, workspace / path, "genbank")
        refs.append(ConstructRef(path.as_posix()))
    originals = [(workspace / ref.path).read_bytes() for ref in refs]
    manager = WorkflowManager(
        BiologyServiceAdapter(workspace, run / "intermediate"), UnavailableSnapGene()
    )
    workflow = manager.start(
        "Assemble two synthetic overlapping fragments into a circular product."
    )
    manager.gibson_assemble(
        workflow.id, fragments=refs, overlaps=[20, 20], name="Gibson_demo"
    )
    gate_checked = False
    try:
        manager.save_construct(
            workflow.id,
            output_path=(run / "premature.gb").as_posix(),
            output_format="genbank",
        )
    except WorkflowError as error:
        if error.code != "validation_required":
            raise
        gate_checked = True
    validation = manager.validate_construct(workflow.id)
    if not validation["valid"]:
        raise RuntimeError("Product failed validation")
    saved = manager.save_construct(
        workflow.id,
        output_path=(run / "assembled.gb").as_posix(),
        output_format="genbank",
    )
    product = load_construct(workspace / saved["construct"]["path"], "genbank")
    checks = {
        "expected_sequence": product.sequence == left + backbone + right + insert,
        "expected_length": len(product.sequence) == 160,
        "circular": product.topology == "circular",
        "source_files_unchanged": originals
        == [(workspace / ref.path).read_bytes() for ref in refs],
        "validation_gate": gate_checked,
        "annotations_preserved": {f.name for f in product.features}
        >= {"Synthetic backbone", "Synthetic insert"},
        "two_junctions_annotated": sum(
            f.name.startswith("Gibson junction") for f in product.features
        )
        == 2,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Independent demo verification failed: {checks}")
    report = {
        "demo": "Synthetic Gibson exact-overlap simulation",
        "fragments_bp": [110, 90],
        "overlaps_bp": [20, 20],
        "product_bp": len(product.sequence),
        "topology": product.topology,
        "checks": checks,
        "product": saved["construct"],
        "limitations": "Pre-oriented fragments; explicit exact overlaps; no primer design or wet-lab efficiency prediction.",
    }
    (workspace / run / "verification.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    (workspace / run / "workflow.json").write_text(
        json.dumps(workflow.to_dict(), indent=2) + "\n"
    )
    print("GIBSON ASSEMBLY — local Python demo (no SnapGene)")
    print("110 bp vector + 90 bp insert - two 20 bp overlaps = 160 bp circular product")
    print(
        "PASS: sequence, length, topology, annotations, junctions, unchanged inputs, validation gate"
    )
    print(f"Product:      {run / 'assembled.gb'}")
    print(f"Verification: {run / 'verification.json'}")
    print(f"Workflow log: {run / 'workflow.json'}")
    print(
        "Synthetic sequence demo; primer design and experimental efficiency are outside this MVP."
    )


if __name__ == "__main__":
    main()
