from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from Bio.Seq import Seq

from agent.bootstrap import UnavailableSnapGene, manager_from_environment
from agent.errors import WorkflowError
from agent.models import ConstructRef
from agent.session import WorkflowManager
from dnamaker.assembly import assemble_gibson
from dnamaker.errors import BiologyError
from dnamaker.io import load_construct, write_construct
from dnamaker.models import Construct, Feature
from dnamaker.service import BiologyServiceAdapter

LEFT = "ACGTCAGTACGATCGTAGCA"
RIGHT = "TGCACTGATCGATGCTACGT"
CORE = "GATTACA" * 10
INSERT = "CCGTA" * 10


def fragments():
    return [
        Construct(name="vector", sequence=LEFT + CORE + RIGHT),
        Construct(name="insert", sequence=RIGHT + INSERT + LEFT),
    ]


def test_circular_product_and_junctions():
    product = assemble_gibson(fragments(), overlaps=[20, 20], name="product")
    assert product.sequence == LEFT + CORE + RIGHT + INSERT
    assert product.topology == "circular"
    assert [(f.start, f.end) for f in product.features] == [(90, 110), (0, 20)]


def test_linear_three_fragments():
    a = Construct(name="a", sequence=CORE + LEFT)
    b = Construct(name="b", sequence=LEFT + INSERT + RIGHT)
    c = Construct(name="c", sequence=RIGHT + CORE)
    product = assemble_gibson(
        [a, b, c], overlaps=[20, 20], name="linear", circular=False
    )
    assert product.sequence == CORE + LEFT + INSERT + RIGHT + CORE
    assert product.topology == "linear"


@pytest.mark.parametrize("strand", [1, -1])
def test_origin_crossing_features_preserve_sequence_after_genbank_roundtrip(
    tmp_path, strand
):
    inputs = fragments()
    # This insert feature crosses the product origin after the final overlap is collapsed.
    inputs[1].features = [
        Feature(name="crossing", type="misc_feature", start=65, end=85, strand=strand)
    ]
    product = assemble_gibson(inputs, overlaps=[20, 20], name="product")
    path = tmp_path / "product.gb"
    write_construct(product, path, "genbank")
    loaded = load_construct(path, "genbank")
    feature = loaded.features[0]
    assert len(feature.parts) == 2
    extracted = "".join(
        str(Seq(loaded.sequence[p.start : p.end]).reverse_complement())
        if strand == -1
        else loaded.sequence[p.start : p.end]
        for p in feature.locations()
    )
    expected = inputs[1].sequence[65:85]
    assert extracted == (
        str(Seq(expected).reverse_complement()) if strand == -1 else expected
    )
    assert "Gibson exact-overlap" in loaded.metadata["comment"]


@pytest.mark.parametrize(
    "overlaps,code",
    [
        ([19, 20], "overlap_mismatch"),
        ([20], "invalid_overlap"),
        ([True, 20], "invalid_overlap"),
        ([0, 20], "invalid_overlap"),
    ],
)
def test_bad_junctions(overlaps, code):
    with pytest.raises(BiologyError) as error:
        assemble_gibson(fragments(), overlaps=overlaps, name="bad")
    assert error.value.code == code


def test_closing_junction_is_checked():
    inputs = fragments()
    inputs[1].sequence = inputs[1].sequence[:-1] + "T"
    with pytest.raises(BiologyError) as error:
        assemble_gibson(inputs, overlaps=[20, 20], name="bad")
    assert error.value.code == "overlap_mismatch"
    assert error.value.details["junction"] == 1


@pytest.mark.parametrize(
    "change,code", [("circular", "fragment_not_linear"), ("N", "invalid_fragment")]
)
def test_invalid_inputs(change, code):
    inputs = fragments()
    if change == "circular":
        inputs[0].topology = change
    else:
        inputs[0].sequence = "N" + inputs[0].sequence[1:]
    with pytest.raises(BiologyError) as error:
        assemble_gibson(inputs, overlaps=[20, 20], name="bad")
    assert error.value.code == code


def test_overlapping_junctions_rejected():
    inputs = [
        Construct(name="a", sequence="A" * 30),
        Construct(name="b", sequence="A" * 30),
    ]
    with pytest.raises(BiologyError) as error:
        assemble_gibson(inputs, overlaps=[20, 20], name="bad")
    assert error.value.code == "overlapping_junctions"


def test_real_workflow_and_biology_only_bootstrap(tmp_path):
    refs = []
    for index, fragment in enumerate(fragments()):
        path = tmp_path / f"fragment-{index}.gb"
        write_construct(fragment, path, "genbank")
        refs.append(ConstructRef(path.name))
    with patch.dict(
        os.environ,
        {
            "DNA_MAKER_BIOLOGY_ADAPTER": "dnamaker.service:create_biology_adapter",
            "DNA_MAKER_WORKSPACE": str(tmp_path),
        },
        clear=True,
    ):
        manager = manager_from_environment()
    workflow = manager.start("Gibson demo")
    manager.read_construct(workflow.id, refs[0])
    manager.validate_construct(workflow.id)
    result = manager.gibson_assemble(
        workflow.id, fragments=refs, overlaps=[20, 20], name="demo"
    )
    assert result["validation_required"]
    with pytest.raises(WorkflowError, match="Validate"):
        manager.save_construct(
            workflow.id, output_path="result.gb", output_format="genbank"
        )
    assert manager.validate_construct(workflow.id)["valid"]
    manager.save_construct(
        workflow.id, output_path="result.gb", output_format="genbank"
    )
    product = load_construct(tmp_path / "result.gb", "genbank")
    assert product.sequence == LEFT + CORE + RIGHT + INSERT
    assert workflow.operations[2].name == "gibson_assemble"
    with pytest.raises(WorkflowError) as error:
        manager.snapgene_convert(workflow.id, output_path="result.dna")
    assert error.value.code == "snapgene_unavailable"


def test_mcp_tool_accepts_structured_fragment_refs(tmp_path):
    import asyncio

    from agent import server

    refs = []
    for index, fragment in enumerate(fragments()):
        path = tmp_path / f"fragment-{index}.gb"
        write_construct(fragment, path, "genbank")
        refs.append({"path": path.name, "format": "genbank"})
    manager = WorkflowManager(BiologyServiceAdapter(tmp_path), UnavailableSnapGene())
    workflow = manager.start("MCP Gibson")
    with patch.object(server, "manager", manager):
        # Exercise FastMCP's JSON-to-dataclass conversion, not just the Python function.
        tool = server.mcp._tool_manager.get_tool("gibson_assemble")
        result = asyncio.run(
            tool.run(
                {
                    "workflow_id": workflow.id,
                    "fragments": refs,
                    "overlaps": [20, 20],
                    "name": "mcp_product",
                }
            )
        )
    assert result["ok"]
    assert result["result"]["validation_required"]


@pytest.mark.parametrize("via_copy", [False, True])
def test_mixed_case_fragments_are_normalized_at_assembly_boundary(via_copy):
    inputs = fragments()
    mixed = RIGHT.lower() + INSERT + LEFT.lower()
    if via_copy:
        inputs[1] = inputs[1].model_copy(update={"sequence": mixed})
    else:
        inputs[1].sequence = mixed
    inputs[1].features = [
        Feature(name="MixedCase label", type="misc_feature", start=20, end=70)
    ]
    product = assemble_gibson(inputs, overlaps=[20, 20], name="MixedCase product")
    assert product.sequence == LEFT + CORE + RIGHT + INSERT
    assert product.sequence.isupper()
    assert inputs[1].sequence == mixed  # Do not mutate the caller's construct.
    assert product.name == "MixedCase product"
    assert product.features[0].name == "MixedCase label"
    assert (product.features[0].start, product.features[0].end) == (110, 160)
