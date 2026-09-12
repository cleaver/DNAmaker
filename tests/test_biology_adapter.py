from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent.models import ConstructRef
from agent.session import WorkflowManager
from dnamaker.errors import BiologyError
from dnamaker.io import write_construct
from dnamaker.models import Construct, Feature
from dnamaker.service import BiologyServiceAdapter, create_biology_adapter

FIXTURES = Path(__file__).parent / "fixtures"


def copy_fixture(tmp_path: Path, name: str) -> str:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    shutil.copy2(FIXTURES / name, inputs / name)
    return f"inputs/{name}"


def json_construct(
    tmp_path: Path, construct: Construct, filename: str = "construct.json"
) -> str:
    path = tmp_path / "inputs" / filename
    path.parent.mkdir(exist_ok=True)
    write_construct(construct, path, "json")
    return f"inputs/{filename}"


def test_read_genbank_returns_shared_summary(tmp_path: Path) -> None:
    adapter = BiologyServiceAdapter(tmp_path)
    path = copy_fixture(tmp_path, "mini_construct.gb")

    summary = adapter.read_construct(ConstructRef(path, "genbank"))

    assert summary.construct.format == "genbank"
    assert summary.construct.name == "pExample"
    assert summary.sequence_length == 30
    assert summary.topology == "circular"
    assert [feature["name"] for feature in summary.features] == [
        "source_0",
        "target",
        "downstream",
    ]
    assert summary.features[1]["start"] == 10
    assert summary.features[1]["end"] == 14


def test_genbank_round_trip_preserves_supported_features(tmp_path: Path) -> None:
    adapter = BiologyServiceAdapter(tmp_path)
    input_path = copy_fixture(tmp_path, "mini_construct.gb")

    saved = adapter.save_construct(
        ConstructRef(input_path, "genbank"),
        output_path="outputs/result.gb",
        output_format="genbank",
    )
    summary = adapter.read_construct(saved)

    assert summary.sequence_length == 30
    assert summary.topology == "circular"
    assert [feature["name"] for feature in summary.features] == [
        "source_0",
        "target",
        "downstream",
    ]
    assert summary.features[1]["qualifiers"]["note"] == ["replace me"]


def test_fasta_has_no_annotations_and_round_trips_sequence(tmp_path: Path) -> None:
    adapter = BiologyServiceAdapter(tmp_path)
    input_path = copy_fixture(tmp_path, "mini_sequence.fasta")

    summary = adapter.read_construct(ConstructRef(input_path, "fasta"))
    saved = adapter.save_construct(
        ConstructRef(input_path, "fasta"),
        output_path="outputs/result.fasta",
        output_format="fasta",
    )
    reread = adapter.read_construct(saved)

    assert summary.topology == "linear"
    assert summary.features == []
    assert reread.sequence_length == 30
    assert reread.features == []


def test_json_round_trip_uses_documented_schema(tmp_path: Path) -> None:
    adapter = BiologyServiceAdapter(tmp_path)
    construct = Construct(
        name="jsonExample",
        sequence="ATGCATGC",
        topology="linear",
        features=[Feature(name="tag", type="misc_feature", start=2, end=6, strand=-1)],
        metadata={"description": "JSON fixture"},
    )
    input_path = json_construct(tmp_path, construct)

    summary = adapter.read_construct(ConstructRef(input_path, "json"))
    saved = adapter.save_construct(
        ConstructRef(input_path, "json"),
        output_path="outputs/result.json",
        output_format="json",
    )
    reread = adapter.read_construct(saved)

    assert summary.features[0]["strand"] == -1
    assert reread.construct.name == "jsonExample"
    assert reread.features == summary.features


def test_replace_region_preserves_input_and_shifts_downstream_features(
    tmp_path: Path,
) -> None:
    adapter = BiologyServiceAdapter(tmp_path)
    input_path = copy_fixture(tmp_path, "mini_construct.gb")
    reference = ConstructRef(input_path, "genbank")
    input_bytes = (tmp_path / input_path).read_bytes()

    result = adapter.replace_region(
        reference,
        target="target",
        replacement_sequence="CCCCCC",
        replacement_name="replacement",
    )
    summary = adapter.read_construct(result)

    assert result.path != reference.path
    assert (tmp_path / input_path).read_bytes() == input_bytes
    replacement = next(
        feature for feature in summary.features if feature["name"] == "replacement"
    )
    downstream = next(
        feature for feature in summary.features if feature["name"] == "downstream"
    )
    assert (replacement["start"], replacement["end"]) == (10, 16)
    assert (downstream["start"], downstream["end"]) == (24, 28)


def test_replace_region_rejects_ambiguous_and_overlapping_targets(
    tmp_path: Path,
) -> None:
    adapter = BiologyServiceAdapter(tmp_path)
    duplicate_path = json_construct(
        tmp_path,
        Construct(
            name="duplicate",
            sequence="ATGCATGC",
            features=[
                Feature(name="target", type="misc_feature", start=0, end=2),
                Feature(name="target", type="misc_feature", start=4, end=6),
            ],
        ),
        "duplicate.json",
    )
    with pytest.raises(BiologyError, match="Multiple features"):
        adapter.replace_region(
            ConstructRef(duplicate_path, "json"),
            target="target",
            replacement_sequence="AA",
            replacement_name=None,
        )

    overlap_path = json_construct(
        tmp_path,
        Construct(
            name="overlap",
            sequence="ATGCATGC",
            features=[
                Feature(name="target", type="misc_feature", start=1, end=4),
                Feature(name="overlap", type="misc_feature", start=3, end=6),
            ],
        ),
        "overlap.json",
    )
    with pytest.raises(BiologyError, match="another feature"):
        adapter.replace_region(
            ConstructRef(overlap_path, "json"),
            target="target",
            replacement_sequence="AA",
            replacement_name=None,
        )


def test_add_annotation_and_restriction_scan(tmp_path: Path) -> None:
    adapter = BiologyServiceAdapter(tmp_path)
    input_path = copy_fixture(tmp_path, "mini_construct.gb")
    reference = ConstructRef(input_path, "genbank")

    annotated = adapter.add_annotation(
        reference, name="promoter", feature_type="promoter", start=0, end=4, strand=1
    )
    summary = adapter.read_construct(annotated)
    sites = adapter.find_restriction_sites(reference, enzyme="BsaI")

    assert summary.features[-1]["name"] == "promoter"
    assert sites == [{"position": 4, "strand": 1, "site": "GGTCTC"}]


def test_circular_restriction_site_can_cross_origin(tmp_path: Path) -> None:
    adapter = BiologyServiceAdapter(tmp_path)
    path = json_construct(
        tmp_path,
        Construct(name="circular", sequence="CTCGGT", topology="circular"),
        "circular.json",
    )

    assert adapter.find_restriction_sites(
        ConstructRef(path, "json"), enzyme="BsaI"
    ) == [{"position": 3, "strand": 1, "site": "GGTCTC"}]


def test_validation_returns_stable_checks_for_invalid_construct(tmp_path: Path) -> None:
    adapter = BiologyServiceAdapter(tmp_path)
    path = json_construct(
        tmp_path,
        Construct(
            name="invalid",
            sequence="ATGX",
            topology="unknown",
            features=[
                Feature(
                    name="bad_bounds", type="misc_feature", start=-1, end=8, strand=0
                ),
            ],
        ),
        "invalid.json",
    )

    result = adapter.validate_construct(ConstructRef(path, "json"))

    assert result.valid is False
    assert [check["name"] for check in result.checks] == [
        "sequence_alphabet",
        "topology",
        "feature_bounds",
        "feature_strands",
    ]
    assert all({"name", "passed"} <= check.keys() for check in result.checks)


def test_unsupported_format_and_invalid_annotation_are_explicit(tmp_path: Path) -> None:
    adapter = BiologyServiceAdapter(tmp_path)
    path = copy_fixture(tmp_path, "mini_construct.gb")
    reference = ConstructRef(path, "genbank")

    with pytest.raises(BiologyError, match="SnapGene"):
        adapter.read_construct(ConstructRef(path, "snapgene"))
    with pytest.raises(BiologyError, match="outside"):
        adapter.add_annotation(
            reference,
            name="bad",
            feature_type="misc_feature",
            start=0,
            end=31,
            strand=1,
        )
    with pytest.raises(BiologyError, match="strand"):
        adapter.add_annotation(
            reference, name="bad", feature_type="misc_feature", start=0, end=2, strand=0
        )


def test_real_adapter_runs_through_workflow_manager(tmp_path: Path) -> None:
    adapter = BiologyServiceAdapter(tmp_path)

    class FakeSnapGene:
        def __init__(self):
            self.converted = []
            self.opened = []

        def convert(self, construct: ConstructRef, *, output_path: str) -> ConstructRef:
            self.converted.append(construct)
            return ConstructRef(output_path, "snapgene", construct.name)

        def render_map(self, construct: ConstructRef, *, output_path: str, size: int = 1200) -> str:
            return output_path

        def open(self, construct: ConstructRef) -> None:
            self.opened.append(construct)

    input_path = copy_fixture(tmp_path, "mini_construct.gb")
    snapgene = FakeSnapGene()
    manager = WorkflowManager(adapter, snapgene)
    workflow = manager.start("Replace target and export it")
    manager.read_construct(workflow.id, ConstructRef(input_path, "genbank"))
    mutation = manager.replace_region(
        workflow.id,
        target="target",
        replacement_sequence="CCCC",
        replacement_name="replacement",
    )

    with pytest.raises(Exception, match="Validate"):
        manager.save_construct(
            workflow.id, output_path="outputs/result.gb", output_format="genbank"
        )

    validation = manager.validate_construct(workflow.id)
    saved = manager.save_construct(
        workflow.id, output_path="outputs/result.gb", output_format="genbank"
    )
    converted = manager.snapgene_convert(
        workflow.id, output_path="outputs/result.dna"
    )
    manager.snapgene_open(workflow.id)

    assert mutation["validation_required"] is True
    assert validation["valid"] is True
    assert saved["construct"]["path"] == "outputs/result.gb"
    assert snapgene.converted[0].format == "genbank"
    assert snapgene.converted[0].path == mutation["construct"]["path"]
    assert converted["construct"]["format"] == "snapgene"
    assert [reference.to_dict() for reference in snapgene.opened] == [
        converted["construct"]
    ]


def test_factory_reads_workspace_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DNA_MAKER_WORKSPACE", str(tmp_path))

    adapter = create_biology_adapter()

    assert adapter.workspace == tmp_path.resolve()
    assert adapter.artifact_dir == (tmp_path / "artifacts" / "biology").resolve()
