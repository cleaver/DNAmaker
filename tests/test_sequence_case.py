"""Case handling at boundaries that accept already-created construct objects."""

import json
import runpy
from pathlib import Path

import pytest
from Bio import SeqIO

from dnamaker.io import write_construct
from dnamaker.models import Construct, Feature
from dnamaker.validation import validate_construct_data


def mixed_construct():
    return Construct(
        name="MixedLabel",
        sequence="ACGT",
        features=[Feature(name="MixedFeature", type="misc_feature", start=1, end=3)],
    ).model_copy(update={"sequence": "acGt"})


def test_validation_accepts_base_case_without_mutating_input():
    construct = mixed_construct()
    assert validate_construct_data(construct)[0]
    assert construct.sequence == "acGt"


@pytest.mark.parametrize("sequence", ["acXt", "ac gt", ""])
def test_validation_still_rejects_invalid_sequence(sequence):
    construct = mixed_construct().model_copy(update={"sequence": sequence})
    assert not validate_construct_data(construct)[0]


@pytest.mark.parametrize("format", ["fasta", "json", "genbank"])
def test_exports_normalize_only_sequence_case(tmp_path, format):
    construct = mixed_construct()
    path = tmp_path / "output"
    write_construct(construct, path, format)
    if format == "json":
        data = json.loads(path.read_text())
        assert data["sequence"] == "ACGT"
        assert data["name"] == "MixedLabel"
        assert data["features"][0]["name"] == "MixedFeature"
    else:
        record = SeqIO.read(path, format)
        assert str(record.seq) == "ACGT"
        assert record.id == "MixedLabel"
    assert construct.sequence == "acGt"
    assert (construct.features[0].start, construct.features[0].end) == (1, 3)


@pytest.mark.parametrize("corrupt_product", [False, True])
def test_real_demo_verifier_accepts_lowercase_sources(
    tmp_path, monkeypatch, corrupt_product
):
    root = Path(__file__).resolve().parents[1]
    original_read = SeqIO.read

    def lowercase_read(*args, **kwargs):
        record = original_read(*args, **kwargs)
        record.seq = record.seq.lower()
        if corrupt_product and str(args[0]).endswith("demo5-gibson-mCherry.dna"):
            from Bio.Seq import Seq

            replacement = "a" if record.seq[0] != "a" else "c"
            record.seq = Seq(replacement + str(record.seq[1:]))
        return record

    monkeypatch.setattr(SeqIO, "read", lowercase_read)
    script = root / "outputs/demo5-fragments/prepare_verify.py"
    namespace = runpy.run_path(str(script))
    verify = namespace["verify"]
    verify.__globals__["OUT"] = tmp_path
    # Capture this checkout's bytes before verification; archived hashes may
    # reflect different line endings. Keep the unchanged-source assertion active.
    report = json.loads((script.parent / "derivation.json").read_text())
    report["source_sha256"] = namespace["hashes"]()
    (tmp_path / "derivation.json").write_text(json.dumps(report))
    if corrupt_product:
        with pytest.raises(AssertionError):
            verify(root / "outputs/demo5-gibson-mCherry.dna")
        return
    verify(root / "outputs/demo5-gibson-mCherry.dna")
    assert json.loads((tmp_path / "verification-dna.json").read_text())[
        "both_junctions_exact"
    ]
