import shutil
from pathlib import Path

import pytest
from Bio import SeqIO

from agent.errors import WorkflowError
from agent.models import ConstructRef
from agent.session import WorkflowManager
from dnamaker.handoff import prepare_handoff
from dnamaker.io import write_construct
from dnamaker.models import Construct, Feature, Location
from dnamaker.service import BiologyServiceAdapter


def test_real_fixture_handoff_and_conversion_gate(tmp_path):
    shutil.copytree(Path(__file__).resolve().parents[1] / "inputs", tmp_path / "inputs")
    report = prepare_handoff(tmp_path)
    original = SeqIO.read(tmp_path / "inputs/pEGFP-N1.gb", "genbank")
    donor = SeqIO.read(tmp_path / "inputs/mCherry.gb", "genbank")
    ref = ConstructRef(**report["construct"])
    result = SeqIO.read(tmp_path / ref.path, "genbank")
    assert result.seq == original.seq[:678] + donor.seq + original.seq[1398:]
    assert len(result) == 4724
    assert result.annotations["topology"] == "circular"
    assert report["validation"]["valid"]
    assert report["restriction_sites"] == [
        {"position": 628, "strand": 1, "site": "GAATTC"}
    ]
    assert len(result.features) == len(original.features)
    for before, after in zip(original.features, result.features):
        label = before.qualifiers.get("label")
        if label == ["EGFP"]:
            assert after.qualifiers["label"] == ["mCherry"]
            assert after.extract(result.seq) == donor.seq
            assert (
                str(after.extract(result.seq).translate(cds=True))
                == donor.features[1].qualifiers["translation"][0]
            )
            assert not {"translation", "product", "note"} & after.qualifiers.keys()
        elif before.type == "source":
            assert int(after.location.end) == len(result)
        else:
            assert before.qualifiers == after.qualifiers
            assert before.extract(original.seq) == after.extract(result.seq)
            delta = -9 if int(before.location.start) >= 1398 else 0
            assert int(after.location.start) == int(before.location.start) + delta
            assert int(after.location.end) == int(before.location.end) + delta

    class RecordingSnapGene:
        def __init__(self):
            self.calls = []

        def convert(self, construct, *, output_path):
            self.calls.append(construct)
            assert (tmp_path / construct.path).is_file()
            return ConstructRef(output_path, "snapgene", construct.name)

    snapgene = RecordingSnapGene()
    manager = WorkflowManager(BiologyServiceAdapter(tmp_path), snapgene)
    workflow = manager.start("Receive handoff and convert")
    manager.read_construct(workflow.id, ref)
    with pytest.raises(WorkflowError, match="Validate"):
        manager.snapgene_convert(workflow.id, output_path="outputs/result.dna")
    assert not snapgene.calls
    assert manager.validate_construct(workflow.id)["valid"]
    manager.snapgene_convert(workflow.id, output_path="outputs/result.dna")
    assert snapgene.calls == [ref]
    manager.add_annotation(
        workflow.id, name="test", feature_type="misc_feature", start=0, end=3, strand=1
    )
    with pytest.raises(WorkflowError, match="Validate"):
        manager.snapgene_convert(workflow.id, output_path="outputs/stale.dna")
    assert snapgene.calls == [ref]


@pytest.mark.parametrize(
    "parts,strand,allowed",
    [
        ([(1, 3), (3, 5)], 1, True),
        ([(3, 5), (1, 3)], -1, True),
        ([(1, 3), (4, 5)], 1, False),
        ([(6, 8), (0, 2)], 1, False),
    ],
)
def test_join_replacement_only_accepts_adjacent_segments(
    tmp_path, parts, strand, allowed
):
    construct = Construct(
        name="joined",
        sequence="ACGTACGT",
        features=[
            Feature(
                name="target",
                type="CDS",
                start=min(p[0] for p in parts),
                end=max(p[1] for p in parts),
                strand=strand,
                parts=[Location(start=start, end=end) for start, end in parts],
            ),
        ],
    )
    write_construct(construct, tmp_path / "input.json", "json")
    adapter = BiologyServiceAdapter(tmp_path)

    def replace():
        return adapter.replace_region(
            ConstructRef("input.json", "json"),
            target="target",
            replacement_sequence="AAA",
            replacement_name="new",
        )

    if allowed:
        result = adapter.read_construct(replace())
        assert result.sequence_length == 7
        assert result.features[0]["strand"] == strand
        assert "parts" not in result.features[0]
    else:
        with pytest.raises(Exception, match="not supported"):
            replace()
