from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

from Bio import SeqIO
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).parent.parent


def test_codex_mcp_stdio_vertical_slice(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    shutil.copy2(PROJECT_ROOT / "inputs/pEGFP-N1.gb", inputs / "pEGFP-N1.gb")
    mCherry = SeqIO.read(PROJECT_ROOT / "inputs/mCherry.gb", "genbank")

    async def run() -> None:
        environment = os.environ.copy()
        environment.update(
            {
                "DNA_MAKER_WORKSPACE": str(tmp_path),
                "DNA_MAKER_BIOLOGY_ADAPTER": "dnamaker.service:create_biology_adapter",
                "DNA_MAKER_SNAPGENE_ADAPTER": "tests.mcp_fakes:create_service",
            }
        )
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "agent.server"],
            env=environment,
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert {"read_construct", "replace_region", "validate_construct", "snapgene_convert", "snapgene_render", "snapgene_open"} <= names

                started = await session.call_tool(
                    "start_workflow", {"request": "Replace target and open the result."}
                )
                workflow_id = started.structuredContent["result"]["workflow_id"]

                read_result = await session.call_tool(
                    "read_construct",
                    {"workflow_id": workflow_id, "path": "inputs/pEGFP-N1.gb"},
                )
                assert read_result.structuredContent["ok"] is True

                failed_edit = await session.call_tool(
                    "replace_region",
                    {
                        "workflow_id": workflow_id,
                        "target": "missing",
                        "replacement_sequence": "CCCC",
                    },
                )
                assert failed_edit.structuredContent == {
                    "ok": False,
                    "error": {
                        "code": "target_not_found",
                        "message": "No feature named 'missing' was found.",
                        "details": {"target": "missing"},
                    },
                }

                await session.call_tool(
                    "replace_region",
                    {
                        "workflow_id": workflow_id,
                        "target": "EGFP",
                        "replacement_sequence": str(mCherry.seq),
                        "replacement_name": "mCherry",
                    },
                )
                validation = await session.call_tool(
                    "validate_construct", {"workflow_id": workflow_id}
                )
                assert validation.structuredContent["result"]["valid"] is True
                converted = await session.call_tool(
                    "snapgene_convert",
                    {"workflow_id": workflow_id, "output_path": "outputs/result.dna"},
                )
                converted_ref = converted.structuredContent["result"]["construct"]
                assert converted_ref["format"] == "snapgene"
                rendered = await session.call_tool(
                    "snapgene_render",
                    {"workflow_id": workflow_id, "output_path": "outputs/result.png"},
                )
                assert rendered.structuredContent["result"]["map_path"] == "outputs/result.png"
                opened = await session.call_tool("snapgene_open", {"workflow_id": workflow_id})
                assert opened.structuredContent["result"]["opened"] == converted_ref

                status = await session.call_tool("workflow_status", {"workflow_id": workflow_id})
                operations = status.structuredContent["result"]["operations"]
                assert [operation["name"] for operation in operations] == [
                    "read_construct",
                    "replace_region",
                    "validate_construct",
                    "snapgene_convert",
                    "snapgene_render",
                    "snapgene_open",
                ]

    asyncio.run(run())
