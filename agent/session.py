"""Execution state and validation gates for one reproducible workflow."""

from __future__ import annotations

from uuid import uuid4

from .adapters import BiologyService, SnapGeneService
from .errors import WorkflowError
from .models import ConstructRef, OperationRecord, WorkflowSession


class WorkflowManager:
    def __init__(self, biology: BiologyService, snapgene: SnapGeneService):
        self.biology = biology
        self.snapgene = snapgene
        self._sessions: dict[str, WorkflowSession] = {}

    def start(self, request: str) -> WorkflowSession:
        if not request.strip():
            raise WorkflowError("invalid_request", "Workflow request must not be empty.")
        session = WorkflowSession(id=str(uuid4()), request=request.strip())
        self._sessions[session.id] = session
        return session

    def get(self, workflow_id: str) -> WorkflowSession:
        try:
            return self._sessions[workflow_id]
        except KeyError as error:
            raise WorkflowError("workflow_not_found", f"Unknown workflow id: {workflow_id}") from error

    def read_construct(self, workflow_id: str, construct: ConstructRef) -> dict:
        session = self.get(workflow_id)
        summary = self.biology.read_construct(construct)
        # Use the adapter's normalized reference (including the construct
        # name and canonical format) for all later provenance checks.
        session.current_construct = summary.construct
        session.validated_construct_path = None
        session.validated_construct = None
        session.snapgene_construct = None
        session.snapgene_source_construct = None
        session.snapgene_map_path = None
        result = summary.to_dict()
        self._record(session, "read_construct", construct.to_dict(), result, destructive=False)
        return result

    def replace_region(self, workflow_id: str, *, target: str, replacement_sequence: str, replacement_name: str | None) -> dict:
        session = self._require_construct(workflow_id)
        result = self.biology.replace_region(session.current_construct, target=target, replacement_sequence=replacement_sequence, replacement_name=replacement_name)
        return self._mutation(session, "replace_region", {"target": target, "replacement_sequence": replacement_sequence, "replacement_name": replacement_name}, result)

    def add_annotation(self, workflow_id: str, *, name: str, feature_type: str, start: int, end: int, strand: int) -> dict:
        session = self._require_construct(workflow_id)
        result = self.biology.add_annotation(session.current_construct, name=name, feature_type=feature_type, start=start, end=end, strand=strand)
        return self._mutation(session, "add_annotation", {"name": name, "feature_type": feature_type, "start": start, "end": end, "strand": strand}, result)

    def find_restriction_sites(self, workflow_id: str, *, enzyme: str) -> dict:
        session = self._require_construct(workflow_id)
        sites = self.biology.find_restriction_sites(session.current_construct, enzyme=enzyme)
        result = {"construct": session.current_construct.to_dict(), "enzyme": enzyme, "sites": sites}
        self._record(session, "find_restriction_sites", {"enzyme": enzyme}, result, destructive=False)
        return result

    def validate_construct(self, workflow_id: str) -> dict:
        session = self._require_construct(workflow_id)
        # A fresh validation is the only authority for downstream actions;
        # discard any older SnapGene artifact before checking the construct.
        session.snapgene_construct = None
        session.snapgene_source_construct = None
        session.snapgene_map_path = None
        result = self.biology.validate_construct(session.current_construct).to_dict()
        if result["valid"]:
            session.validated_construct_path = session.current_construct.path
            session.validated_construct = session.current_construct
        else:
            session.validated_construct_path = None
            session.validated_construct = None
        self._record(session, "validate_construct", {}, result, destructive=False)
        return result

    def save_construct(self, workflow_id: str, *, output_path: str, output_format: str) -> dict:
        session = self._require_validated_construct(workflow_id)
        saved = self.biology.save_construct(session.current_construct, output_path=output_path, output_format=output_format)
        result = {"construct": saved.to_dict()}
        self._record(session, "save_construct", {"output_path": output_path, "output_format": output_format}, result, destructive=False)
        return result

    def snapgene_convert(self, workflow_id: str, *, output_path: str) -> dict:
        session = self._require_validated_construct(workflow_id)
        if session.current_construct.format != "genbank":
            raise WorkflowError(
                "genbank_required",
                "SnapGene integration requires a validated GenBank ConstructRef.",
                {"format": session.current_construct.format},
            )
        converted = self.snapgene.convert(session.current_construct, output_path=output_path)
        if converted.format != "snapgene":
            raise WorkflowError(
                "invalid_snapgene_reference",
                "SnapGene conversion must return a ConstructRef with format='snapgene'.",
                {"format": converted.format},
            )
        session.snapgene_construct = converted
        session.snapgene_source_construct = session.current_construct
        session.snapgene_map_path = None
        result = {"construct": converted.to_dict()}
        self._record(session, "snapgene_convert", {"output_path": output_path}, result, destructive=False)
        return result

    def snapgene_render(self, workflow_id: str, *, output_path: str, size: int = 1200) -> dict:
        """Render a map for the exact SnapGene artifact converted in this run."""
        session = self._require_validated_construct(workflow_id)
        construct = self._require_snapgene_construct(session)
        map_path = self.snapgene.render_map(construct, output_path=output_path, size=size)
        session.snapgene_map_path = map_path
        result = {"construct": construct.to_dict(), "map_path": map_path, "size": size}
        self._record(session, "snapgene_render", {"output_path": output_path, "size": size}, result, destructive=False)
        return result

    def snapgene_open(self, workflow_id: str, *, path: str | None = None, format: str = "snapgene") -> dict:
        session = self._require_validated_construct(workflow_id)
        construct = self._require_snapgene_construct(session)
        if path is not None and (path != construct.path or format != construct.format):
            raise WorkflowError(
                "snapgene_reference_mismatch",
                "Open must use the exact ConstructRef returned by snapgene_convert.",
                {"converted": construct.to_dict(), "requested": {"path": path, "format": format}},
            )
        self.snapgene.open(construct)
        result = {"opened": construct.to_dict()}
        self._record(session, "snapgene_open", construct.to_dict(), result, destructive=False)
        return result

    def _require_construct(self, workflow_id: str) -> WorkflowSession:
        session = self.get(workflow_id)
        if session.current_construct is None:
            raise WorkflowError("construct_not_loaded", "Call read_construct before this operation.")
        return session

    def _require_validated_construct(self, workflow_id: str) -> WorkflowSession:
        session = self._require_construct(workflow_id)
        if session.validated_construct != session.current_construct:
            raise WorkflowError("validation_required", "Validate the current construct successfully before saving or using SnapGene.")
        return session

    @staticmethod
    def _require_snapgene_construct(session: WorkflowSession) -> ConstructRef:
        if session.snapgene_construct is None or session.snapgene_source_construct != session.current_construct:
            raise WorkflowError(
                "snapgene_conversion_required",
                "Convert the current validated GenBank construct before this SnapGene operation.",
            )
        return session.snapgene_construct

    def _mutation(self, session: WorkflowSession, name: str, input: dict, construct: ConstructRef) -> dict:
        session.current_construct = construct
        session.validated_construct_path = None
        session.validated_construct = None
        session.snapgene_construct = None
        session.snapgene_source_construct = None
        session.snapgene_map_path = None
        result = {"construct": construct.to_dict(), "validation_required": True}
        self._record(session, name, input, result, destructive=True)
        return result

    @staticmethod
    def _record(session: WorkflowSession, name: str, input: dict, output: dict, destructive: bool) -> None:
        session.operations.append(OperationRecord(name=name, input=input, output=output, destructive=destructive))
