"""The stdio MCP server exposed to Codex.

The component owners inject real adapters by calling ``set_manager`` during
application startup. Until then every domain call fails explicitly instead of
silently using a fake biology implementation.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from .bootstrap import manager_from_environment
from .errors import WorkflowError
from .models import ConstructRef
from .session import WorkflowManager


class UnavailableBiology:
    def __getattr__(self, name: str) -> Any:
        def unavailable(*args: Any, **kwargs: Any) -> Any:
            raise WorkflowError("biology_unavailable", "The biology adapter has not been configured.")

        return unavailable


class UnavailableSnapGene:
    def __getattr__(self, name: str) -> Any:
        def unavailable(*args: Any, **kwargs: Any) -> Any:
            raise WorkflowError("snapgene_unavailable", "The SnapGene adapter has not been configured.")

        return unavailable


mcp = FastMCP("DNA Maker")
manager = WorkflowManager(UnavailableBiology(), UnavailableSnapGene())


def set_manager(new_manager: WorkflowManager) -> None:
    """Dependency-injection seam used by the production bootstrap and tests."""
    global manager
    manager = new_manager


def _run(callable_: Any) -> dict[str, Any]:
    try:
        return {"ok": True, "result": callable_()}
    except WorkflowError as error:
        return error.to_dict()
    except Exception as error:  # noqa: BLE001 - adapters must not crash the MCP transport
        # BiologyError and SnapGene's domain errors intentionally remain
        # ordinary exceptions at the adapter boundary. Preserve their stable
        # code/message/details when translating them to MCP JSON.
        return WorkflowError(
            getattr(error, "code", "adapter_error"),
            getattr(error, "message", str(error)),
            getattr(error, "details", {}),
        ).to_dict()


@mcp.tool()
def start_workflow(request: str) -> dict[str, Any]:
    """Create an immediately executable workflow and return its id."""
    return _run(lambda: manager.start(request).to_dict())


@mcp.tool()
def workflow_status(workflow_id: str) -> dict[str, Any]:
    """Return the full, reproducible operation log for a workflow."""
    return _run(lambda: manager.get(workflow_id).to_dict())


@mcp.tool()
def read_construct(workflow_id: str, path: str, format: str = "genbank", name: str | None = None) -> dict[str, Any]:
    """Inspect a GenBank/FASTA construct before performing any mutation."""
    return _run(lambda: manager.read_construct(workflow_id, ConstructRef(path=path, format=format, name=name)))  # type: ignore[arg-type]


@mcp.tool()
def replace_region(workflow_id: str, target: str, replacement_sequence: str, replacement_name: str | None = None) -> dict[str, Any]:
    """Replace a named target; validation becomes required afterwards."""
    return _run(lambda: manager.replace_region(workflow_id, target=target, replacement_sequence=replacement_sequence, replacement_name=replacement_name))


@mcp.tool()
def add_annotation(workflow_id: str, name: str, feature_type: str, start: int, end: int, strand: int = 1) -> dict[str, Any]:
    """Add a feature using 0-based, end-exclusive coordinates; validate afterwards."""
    return _run(lambda: manager.add_annotation(workflow_id, name=name, feature_type=feature_type, start=start, end=end, strand=strand))


@mcp.tool()
def find_restriction_sites(workflow_id: str, enzyme: str) -> dict[str, Any]:
    """Run read-only restriction-site analysis against the current construct."""
    return _run(lambda: manager.find_restriction_sites(workflow_id, enzyme=enzyme))


@mcp.tool()
def validate_construct(workflow_id: str) -> dict[str, Any]:
    """Validate the current construct. A successful result unlocks export actions."""
    return _run(lambda: manager.validate_construct(workflow_id))


@mcp.tool()
def save_construct(workflow_id: str, output_path: str, output_format: str = "genbank") -> dict[str, Any]:
    """Save the current construct only after it has validated successfully."""
    return _run(lambda: manager.save_construct(workflow_id, output_path=output_path, output_format=output_format))


@mcp.tool()
def snapgene_convert(workflow_id: str, output_path: str) -> dict[str, Any]:
    """Convert the validated construct to a SnapGene artifact."""
    return _run(lambda: manager.snapgene_convert(workflow_id, output_path=output_path))


@mcp.tool()
def snapgene_render(workflow_id: str, output_path: str, size: int = 1200) -> dict[str, Any]:
    """Render a map for the exact SnapGene artifact converted in this workflow."""
    return _run(lambda: manager.snapgene_render(workflow_id, output_path=output_path, size=size))


@mcp.tool()
def snapgene_open(workflow_id: str, path: str | None = None, format: str = "snapgene") -> dict[str, Any]:
    """Ask the SnapGene adapter to open an existing artifact."""
    return _run(lambda: manager.snapgene_open(workflow_id, path=path, format=format))


def main() -> None:
    # Configuration is optional during independent development. Without it,
    # tools return explicit unavailable-adapter errors rather than failing MCP
    # initialization.
    try:
        set_manager(manager_from_environment())
    except WorkflowError:
        pass
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
