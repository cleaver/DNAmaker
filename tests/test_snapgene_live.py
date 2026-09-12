"""Opt-in real SnapGene tests. Originals are hashed and never edited.

Set DNA_MAKER_LIVE_SNAPGENE=1; optionally DNA_MAKER_LIVE_OPEN=1 to leave
the resulting document open. Close SnapGene yourself before running.
"""

import hashlib
import json
import os
import re
import struct
import unittest
from pathlib import Path
from uuid import uuid4

from agent.models import ConstructRef
from snapgene import DesktopSnapGeneService


def genbank_snapshot(path):
    """Compare sequence, topology and features, ignoring display colors/line whitespace."""
    text = path.read_text(encoding="utf-8-sig")
    features = text.split("FEATURES", 1)[1].split("ORIGIN", 1)[0]
    # SnapGene adds a default source-feature color and trims trailing whitespace.
    # Retain all biological feature locations, labels, directions and qualifiers.
    features = "\n".join(line.rstrip() for line in features.splitlines()
                         if not re.fullmatch(r'\s*/note="color: #[0-9a-fA-F]{6}"\s*', line))
    sequence = re.sub(r"[^a-zA-Z]", "", text.split("ORIGIN", 1)[1].split("//", 1)[0]).upper()
    topology = re.search(r"\b(circular|linear)\b", text.splitlines()[0]).group(1)
    return {"sequence": sequence, "topology": topology, "features": features.strip()}


@unittest.skipUnless(os.environ.get("DNA_MAKER_LIVE_SNAPGENE") == "1", "Set DNA_MAKER_LIVE_SNAPGENE=1 for real desktop tests")
class SnapGeneLiveTests(unittest.TestCase):
    def test_demo_roundtrip_export_map_and_optional_open(self):
        root = Path(__file__).resolve().parents[1]
        service = DesktopSnapGeneService(root)
        run = f"artifacts/snapgene-live-{uuid4().hex[:8]}"
        results = []
        for filename in ("backbones/pEGFP-N1.dna", "genes/mCherry.dna"):
            source = ConstructRef(f"snapgene-demo-files/{filename}", "snapgene")
            before = hashlib.sha256((root / source.path).read_bytes()).hexdigest()
            stem = Path(filename).stem
            gb = service.export(source, output_path=f"{run}/{stem}.gb")
            dna = service.convert(gb, output_path=f"{run}/{stem}-roundtrip.dna")
            again = service.export(dna, output_path=f"{run}/{stem}-roundtrip.gb")
            snapshot = genbank_snapshot(root / gb.path)
            self.assertEqual(snapshot, genbank_snapshot(root / again.path))
            fasta = service.export(dna, output_path=f"{run}/{stem}.fasta", output_format="fasta")
            fasta_sequence = "".join((root / fasta.path).read_text().splitlines()[1:]).upper()
            self.assertEqual(snapshot["sequence"], fasta_sequence)
            png = service.render_map(dna, output_path=f"{run}/{stem}.png")
            with (root / png).open("rb") as image:
                header = image.read(24)
            self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", header[16:24])
            self.assertGreater(width, 100)
            self.assertGreater(height, 100)
            self.assertEqual(before, hashlib.sha256((root / source.path).read_bytes()).hexdigest())
            results.append({"input": source.to_dict(), "genbank": gb.to_dict(), "snapgene": dna.to_dict(),
                            "map": png, "sequence_length": len(snapshot["sequence"]), "topology": snapshot["topology"],
                            "features_preserved": True, "input_sha256": before})
        if os.environ.get("DNA_MAKER_LIVE_OPEN") == "1":
            service.open(ConstructRef(**results[0]["snapgene"]))
        print(json.dumps({"live_snapgene": "passed", "artifacts": results}))


if __name__ == "__main__":
    unittest.main()
