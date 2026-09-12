from contextlib import nullcontext
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agent.errors import WorkflowError
from agent.models import ConstructRef
from snapgene.adapter import DesktopSnapGeneService


DNA = b"\x09\x00\x00\x00\x0eSnapGene\x00\x01\x00\x01\x00\x01"


class SnapGeneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "input.gb").write_text("LOCUS       test 4 bp DNA linear\nORIGIN\n        1 atgc\n//\n")
        self.ref = ConstructRef("input.gb", "genbank", "test")
        self.service = DesktopSnapGeneService(self.root, "SnapGene.exe", open_timeout=0.01)

    def assert_code(self, code, action):
        with self.assertRaises(WorkflowError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)

    @staticmethod
    def run_success(command, **kwargs):
        destination = Path(command[command.index("--output") + 1])
        if "--createPreview" in command:
            destination.write_bytes(b"\x89PNG\r\n\x1a\n" + b"image")
        elif command[command.index("--convert") + 1] == "GenBank - SnapGene":
            destination.with_suffix(".gbk").write_text("LOCUS       test\n")
        elif command[command.index("--convert") + 1] == "FASTA":
            destination.with_suffix(".fa").write_text(">test\nATGC\n")
        else:
            destination.write_bytes(DNA)
        return subprocess.CompletedProcess(command, 0, "", "")

    def test_convert_returns_shared_ref_and_preserves_input(self):
        before = (self.root / "input.gb").read_bytes()
        with patch.object(self.service, "_job", return_value=nullcontext()), patch("snapgene.adapter.subprocess.run", side_effect=self.run_success):
            result = self.service.convert(self.ref, output_path="outputs/result.dna")
        self.assertEqual(result, ConstructRef("outputs/result.dna", "snapgene", "test"))
        self.assertEqual((self.root / "input.gb").read_bytes(), before)
        self.assertEqual((self.root / result.path).read_bytes(), DNA)

    def test_export_handles_snapgene_gbk_suffix(self):
        with patch.object(self.service, "_job", return_value=nullcontext()), patch("snapgene.adapter.subprocess.run", side_effect=self.run_success):
            result = self.service.export(self.ref, output_path="export.gb")
        self.assertTrue((self.root / "export.gb").is_file())
        self.assertEqual(result.format, "genbank")

    def test_export_handles_snapgene_fa_suffix(self):
        with patch.object(self.service, "_job", return_value=nullcontext()), patch("snapgene.adapter.subprocess.run", side_effect=self.run_success):
            result = self.service.export(self.ref, output_path="export.fasta", output_format="fasta")
        self.assertEqual((self.root / result.path).read_text(), ">test\nATGC\n")

    def test_refuses_overwrite_and_workspace_escape(self):
        (self.root / "existing.dna").write_bytes(DNA)
        self.assert_code("snapgene_output_exists", lambda: self.service.convert(self.ref, output_path="existing.dna"))
        self.assert_code("snapgene_invalid_path", lambda: self.service.convert(self.ref, output_path="../outside.dna"))
        self.assert_code("snapgene_invalid_path", lambda: self.service.open(ConstructRef("../outside.gb")))
        self.assertEqual((self.root / "existing.dna").read_bytes(), DNA)

    def test_rejects_missing_input_json_and_wrong_suffix(self):
        self.assert_code("snapgene_input_not_found", lambda: self.service.open(ConstructRef("missing.gb")))
        self.assert_code("snapgene_format_unsupported", lambda: self.service.open(ConstructRef("input.gb", "json")))
        self.assert_code("snapgene_invalid_output", lambda: self.service.convert(self.ref, output_path="result.gb"))

    def test_zero_exit_without_file_is_failure(self):
        with patch.object(self.service, "_job", return_value=nullcontext()), patch("snapgene.adapter.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            self.assert_code("snapgene_output_missing", lambda: self.service.convert(self.ref, output_path="result.dna"))
        self.assertFalse((self.root / "result.dna").exists())

    def test_timeout_and_cli_failure_do_not_publish(self):
        for effect, code in [(subprocess.TimeoutExpired("SnapGene", 1), "snapgene_timeout"),
                             (subprocess.CompletedProcess([], 1, "", "bad input"), "snapgene_command_failed")]:
            kwargs = {"side_effect": effect} if isinstance(effect, Exception) else {"return_value": effect}
            with patch.object(self.service, "_job", return_value=nullcontext()), patch("snapgene.adapter.subprocess.run", **kwargs):
                self.assert_code(code, lambda: self.service.convert(self.ref, output_path="result.dna"))
            self.assertFalse((self.root / "result.dna").exists())

    @unittest.skipUnless(os.name == "nt", "Windows byte-range locking")
    def test_existing_desktop_is_never_killed(self):
        with patch.object(self.service, "_check_installation"), patch.object(self.service, "_process_ids", return_value={123}), patch("snapgene.adapter.subprocess.run") as run:
            self.assert_code("snapgene_busy", lambda: self.service.convert(self.ref, output_path="result.dna"))
            run.assert_not_called()

    def test_open_requires_matching_document_window(self):
        with patch.object(self.service, "_job", return_value=nullcontext()), patch("snapgene.adapter.subprocess.Popen"), patch.object(self.service, "_document_windows", return_value=[{"title": "input.gb (Linear / 4 bp)", "pid": 1}]):
            self.assertIsNone(self.service.open(self.ref))

    def test_open_does_not_claim_success_for_unrelated_window(self):
        with patch.object(self.service, "_job", return_value=nullcontext()), patch("snapgene.adapter.subprocess.Popen") as process, patch.object(self.service, "_document_windows", return_value=[{"title": "Registration", "pid": 1}]):
            process.return_value.poll.return_value = None
            self.assert_code("snapgene_open_unconfirmed", lambda: self.service.open(self.ref))

    def test_map_requires_dna_and_validates_png(self):
        self.assert_code("snapgene_format_unsupported", lambda: self.service.render_map(self.ref, output_path="map.png"))
        (self.root / "input.dna").write_bytes(DNA)
        with patch.object(self.service, "_job", return_value=nullcontext()), patch("snapgene.adapter.subprocess.run", side_effect=self.run_success):
            self.assertEqual(self.service.render_map(ConstructRef("input.dna", "snapgene"), output_path="map.png"), "map.png")

    def test_invalid_output_is_not_published(self):
        def corrupt(command, **kwargs):
            Path(command[command.index("--output") + 1]).write_bytes(b"not DNA")
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch.object(self.service, "_job", return_value=nullcontext()), patch("snapgene.adapter.subprocess.run", side_effect=corrupt):
            self.assert_code("snapgene_invalid_artifact", lambda: self.service.convert(self.ref, output_path="bad.dna"))
        self.assertFalse((self.root / "bad.dna").exists())

    def test_racing_output_is_preserved(self):
        def racing(command, **kwargs):
            result = self.run_success(command, **kwargs)
            (self.root / "result.dna").write_bytes(b"other operation")
            return result
        with patch.object(self.service, "_job", return_value=nullcontext()), patch("snapgene.adapter.subprocess.run", side_effect=racing):
            self.assert_code("snapgene_output_exists", lambda: self.service.convert(self.ref, output_path="result.dna"))
        self.assertEqual((self.root / "result.dna").read_bytes(), b"other operation")


if __name__ == "__main__":
    unittest.main()
