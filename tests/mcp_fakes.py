"""Minimal SnapGene service used by the stdio MCP integration test."""

from agent.models import ConstructRef


class FakeSnapGeneService:
    def convert(self, construct: ConstructRef, *, output_path: str) -> ConstructRef:
        return ConstructRef(output_path, "snapgene", construct.name)

    def render_map(self, construct: ConstructRef, *, output_path: str, size: int = 1200) -> str:
        return output_path

    def open(self, construct: ConstructRef) -> None:
        return None


def create_service() -> FakeSnapGeneService:
    return FakeSnapGeneService()
