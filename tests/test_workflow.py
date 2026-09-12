from __future__ import annotations

import unittest

from agent.errors import WorkflowError
from agent.models import ConstructRef, ConstructSummary, ValidationResult
from agent.session import WorkflowManager


class FakeBiology:
    def read_construct(self, construct):
        return ConstructSummary(construct=construct, sequence_length=1000, topology="circular")

    def replace_region(self, construct, *, target, replacement_sequence, replacement_name):
        return ConstructRef(path="artifacts/replaced.gb", name="pExample")

    def add_annotation(self, construct, **kwargs):
        return ConstructRef(path="artifacts/annotated.gb", name="pExample")

    def find_restriction_sites(self, construct, *, enzyme):
        return [{"position": 42, "strand": 1}]

    def validate_construct(self, construct):
        return ValidationResult(valid=True, checks=[{"name": "sequence", "passed": True}])

    def save_construct(self, construct, *, output_path, output_format):
        return ConstructRef(path=output_path, format=output_format, name="pExample")


class FakeSnapGene:
    def __init__(self):
        self.opened = []

    def convert(self, construct, *, output_path):
        return ConstructRef(path=output_path, format="snapgene", name=construct.name)

    def render_map(self, construct, *, output_path, size=1200):
        return output_path

    def open(self, construct):
        self.opened.append(construct.path)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.snapgene = FakeSnapGene()
        self.manager = WorkflowManager(FakeBiology(), self.snapgene)
        self.workflow = self.manager.start("Replace GFP with mCherry and open it.")

    def test_core_workflow_is_logged_and_validation_gated(self):
        workflow_id = self.workflow.id
        self.manager.read_construct(workflow_id, ConstructRef("inputs/example.gb"))
        self.manager.replace_region(workflow_id, target="GFP", replacement_sequence="ATGC", replacement_name="mCherry")
        self.manager.add_annotation(workflow_id, name="CMV", feature_type="promoter", start=10, end=50, strand=1)
        sites = self.manager.find_restriction_sites(workflow_id, enzyme="BsaI")
        self.assertEqual(sites["sites"][0]["position"], 42)

        with self.assertRaisesRegex(Exception, "Validate"):
            self.manager.save_construct(workflow_id, output_path="outputs/result.gb", output_format="genbank")

        self.assertTrue(self.manager.validate_construct(workflow_id)["valid"])
        saved = self.manager.save_construct(workflow_id, output_path="outputs/result.gb", output_format="genbank")
        converted = self.manager.snapgene_convert(workflow_id, output_path="outputs/result.dna")
        self.manager.snapgene_open(workflow_id, path=converted["construct"]["path"])

        self.assertEqual(saved["construct"]["path"], "outputs/result.gb")
        self.assertEqual(self.snapgene.opened, ["outputs/result.dna"])
        self.assertEqual([x.name for x in self.workflow.operations], [
            "read_construct", "replace_region", "add_annotation", "find_restriction_sites",
            "validate_construct", "save_construct", "snapgene_convert", "snapgene_open",
        ])

    def test_mutation_requires_a_loaded_construct(self):
        with self.assertRaisesRegex(Exception, "read_construct"):
            self.manager.replace_region(self.workflow.id, target="GFP", replacement_sequence="ATGC", replacement_name=None)

    def test_open_requires_the_validated_conversion_from_this_workflow(self):
        workflow_id = self.workflow.id
        self.manager.read_construct(workflow_id, ConstructRef("inputs/example.gb"))
        self.manager.validate_construct(workflow_id)

        with self.assertRaisesRegex(WorkflowError, "Convert") as caught:
            self.manager.snapgene_open(workflow_id, path="outputs/arbitrary.dna")
        self.assertEqual(caught.exception.code, "snapgene_conversion_required")

        converted = self.manager.snapgene_convert(workflow_id, output_path="outputs/result.dna")
        rendered = self.manager.snapgene_render(workflow_id, output_path="outputs/result.png")
        self.assertEqual(rendered["map_path"], "outputs/result.png")
        with self.assertRaisesRegex(WorkflowError, "exact ConstructRef") as caught:
            self.manager.snapgene_open(workflow_id, path="outputs/other.dna")
        self.assertEqual(caught.exception.code, "snapgene_reference_mismatch")

        opened = self.manager.snapgene_open(workflow_id)
        self.assertEqual(opened["opened"], converted["construct"])
