"""Small, dependency-free contract shared by MCP tools and component adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ConstructRef:
    """A construct artifact. Paths are relative to the MCP server's workspace."""

    path: str
    format: Literal["genbank", "fasta", "snapgene", "json"] = "genbank"
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConstructSummary:
    construct: ConstructRef
    sequence_length: int
    topology: Literal["circular", "linear"]
    features: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    checks: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OperationRecord:
    name: str
    input: dict[str, Any]
    output: dict[str, Any]
    destructive: bool
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowSession:
    id: str
    request: str
    created_at: str = field(default_factory=utc_now)
    current_construct: ConstructRef | None = None
    validated_construct_path: str | None = None
    validated_construct: ConstructRef | None = None
    snapgene_construct: ConstructRef | None = None
    snapgene_source_construct: ConstructRef | None = None
    snapgene_map_path: str | None = None
    operations: list[OperationRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.id,
            "request": self.request,
            "created_at": self.created_at,
            "current_construct": self.current_construct.to_dict()
            if self.current_construct
            else None,
            "validated_construct_path": self.validated_construct_path,
            "validated_construct": self.validated_construct.to_dict()
            if self.validated_construct
            else None,
            "snapgene_construct": self.snapgene_construct.to_dict()
            if self.snapgene_construct
            else None,
            "snapgene_source_construct": self.snapgene_source_construct.to_dict()
            if self.snapgene_source_construct
            else None,
            "snapgene_map_path": self.snapgene_map_path,
            "operations": [operation.to_dict() for operation in self.operations],
        }
