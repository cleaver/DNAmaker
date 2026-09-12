"""Live stdio MCP integration: pEGFP-N1 EGFP replacement with mCherry.

Run from the project root with SnapGene closed:
    .venv/Scripts/python -m snapgene.mcp_vertical_slice
Uses the actual server process and real adapters; no fake SnapGene service.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from Bio import SeqIO
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .vertical_slice import require


async def run(output_prefix: str | None = None) -> dict:
    root = Path.cwd().resolve()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    folder = root / "artifacts" / f"mcp-live-{stamp}"
    folder.mkdir(parents=True, exist_ok=False)
    relative = folder.relative_to(root).as_posix()
    stem = f"pEGFP-N1-mCherry-{stamp}"
    output_base = output_prefix or f"{relative}/{stem}"
    for extension in ("gb", "dna", "png"):
        destination = (root / f"{output_base}.{extension}").resolve()
        require(
            destination.is_relative_to(root), "Outputs must stay inside the workspace."
        )
        require(not destination.exists(), f"Output already exists: {destination}")
    inputs = ["inputs/pEGFP-N1.gb", "inputs/mCherry.gb"]
    hashes = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in inputs}
    backbone = SeqIO.read(root / inputs[0], "genbank")
    donor = SeqIO.read(root / inputs[1], "genbank")
    target = next(f for f in backbone.features if f.qualifiers.get("label") == ["EGFP"])
    donor_feature = next(
        f
        for f in donor.features
        if f.type == "CDS" and f.qualifiers.get("label") == ["mCherry"]
    )
    replacement = str(donor_feature.extract(donor.seq))
    start, end = int(target.location.start), int(target.location.end)
    expected = str(backbone.seq[:start]) + replacement + str(backbone.seq[end:])
    environment = os.environ.copy()
    environment.update(
        {
            "DNA_MAKER_WORKSPACE": str(root),
            "DNA_MAKER_BIOLOGY_ARTIFACT_DIR": f"{relative}/biology",
            "DNA_MAKER_BIOLOGY_ADAPTER": "dnamaker.service:create_biology_adapter",
            "DNA_MAKER_SNAPGENE_ADAPTER": "snapgene.adapter:create_service",
        }
    )
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "agent.server"], env=environment, cwd=root
    )
    report = {
        "status": "running",
        "transport": "MCP stdio",
        "inputs": inputs,
        "input_sha256": hashes,
        "adapters": {
            k: environment[k]
            for k in ("DNA_MAKER_BIOLOGY_ADAPTER", "DNA_MAKER_SNAPGENE_ADAPTER")
        },
        "artifact_directory": relative,
        "adapter_errors": [],
        "warnings": [],
    }
    calls = []
    workflow_id = None
    try:
        with (folder / "server.stderr.log").open("w", encoding="utf-8") as errors:
            async with stdio_client(parameters, errlog=errors) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    report["available_tools"] = [
                        t.name for t in (await session.list_tools()).tools
                    ]

                    async def call(tool_name: str, **arguments):
                        response = await session.call_tool(tool_name, arguments)
                        payload = response.structuredContent
                        if payload is None:
                            payload = json.loads(
                                next(
                                    c.text for c in response.content if c.type == "text"
                                )
                            )
                        calls.append(
                            {
                                "tool": tool_name,
                                "arguments": arguments,
                                "response": payload,
                            }
                        )
                        if response.isError or not payload.get("ok"):
                            report["adapter_errors"].append(
                                {"tool": tool_name, "error": payload}
                            )
                            raise RuntimeError(f"{tool_name}: {json.dumps(payload)}")
                        return payload["result"]

                    try:
                        donor_workflow = await call(
                            "start_workflow",
                            request="Inspect the mCherry donor GenBank fixture.",
                        )
                        await call(
                            "read_construct",
                            workflow_id=donor_workflow["workflow_id"],
                            path=inputs[1],
                        )
                        started = await call(
                            "start_workflow",
                            request="Replace EGFP with the mCherry CDS, validate, save, convert, render and open in SnapGene. Sequence replacement only; no Gibson simulation.",
                        )
                        workflow_id = started["workflow_id"]
                        report["workflow_id"] = workflow_id
                        await call(
                            "read_construct", workflow_id=workflow_id, path=inputs[0]
                        )
                        await call(
                            "replace_region",
                            workflow_id=workflow_id,
                            target="EGFP",
                            replacement_sequence=replacement,
                            replacement_name="mCherry",
                        )
                        sites = await call(
                            "find_restriction_sites",
                            workflow_id=workflow_id,
                            enzyme="EcoRI",
                        )
                        validation = await call(
                            "validate_construct", workflow_id=workflow_id
                        )
                        require(
                            validation["valid"], "Modified construct failed validation."
                        )
                        saved = await call(
                            "save_construct",
                            workflow_id=workflow_id,
                            output_path=f"{output_base}.gb",
                            output_format="genbank",
                        )
                        report["genbank"] = saved["construct"]["path"]
                        # Save returns a new ref; explicitly revalidate that exact file.
                        await call(
                            "read_construct",
                            workflow_id=workflow_id,
                            **saved["construct"],
                        )
                        validation = await call(
                            "validate_construct", workflow_id=workflow_id
                        )
                        require(
                            validation["valid"], "Saved GenBank failed revalidation."
                        )
                        converted = await call(
                            "snapgene_convert",
                            workflow_id=workflow_id,
                            output_path=f"{output_base}.dna",
                        )
                        report["snapgene"] = converted["construct"]["path"]
                        rendered = await call(
                            "snapgene_render",
                            workflow_id=workflow_id,
                            output_path=f"{output_base}.png",
                        )
                        report["map"] = rendered["map_path"]

                        # Independently read actual artifacts, without bypassing tool actions.
                        genbank = SeqIO.read(root / report["genbank"], "genbank")
                        dna = SeqIO.read(root / report["snapgene"], "snapgene")
                        for record in (genbank, dna):
                            require(
                                str(record.seq).upper() == expected.upper(),
                                "Replacement sequence or flanking vector changed unexpectedly.",
                            )
                            require(
                                record.annotations.get("topology") == "circular",
                                "Circular topology was lost.",
                            )
                            matches = [
                                f
                                for f in record.features
                                if f.qualifiers.get("label") == ["mCherry"]
                            ]
                            require(
                                len(matches) == 1,
                                "Expected exactly one mCherry feature.",
                            )
                            require(
                                int(matches[0].location.start) == start
                                and int(matches[0].location.end)
                                == start + len(replacement),
                                "mCherry feature coordinates differ.",
                            )
                            require(
                                matches[0].location.strand == 1,
                                "mCherry strand differs.",
                            )
                            require(
                                not any(
                                    f.qualifiers.get("label") == ["EGFP"]
                                    for f in record.features
                                ),
                                "Old EGFP feature remains.",
                            )
                        cherry = next(
                            f
                            for f in genbank.features
                            if f.qualifiers.get("label") == ["mCherry"]
                        )
                        translation = cherry.qualifiers.get("translation", [None])[0]
                        if translation and translation != str(
                            cherry.extract(genbank.seq).translate()
                        ).rstrip("*"):
                            report["warnings"].append(
                                "Saved mCherry CDS retains an outdated translation qualifier from EGFP; biology validation does not check CDS translation."
                            )
                        if "EGFP" in str(cherry.qualifiers):
                            report["warnings"].append(
                                "Saved mCherry CDS retains EGFP descriptive qualifiers; Person 2 should refresh replacement metadata."
                            )
                        with (root / report["map"]).open("rb") as png:
                            header = png.read(24)
                        require(
                            header[:8] == b"\x89PNG\r\n\x1a\n", "Output is not PNG."
                        )
                        width, height = struct.unpack(">II", header[16:24])
                        require(
                            width > 100 and height > 100, "PNG dimensions are invalid."
                        )
                        require(
                            hashes
                            == {
                                p: hashlib.sha256((root / p).read_bytes()).hexdigest()
                                for p in inputs
                            },
                            "An input fixture changed.",
                        )
                        report.update(
                            {
                                "validation": validation,
                                "sequence_length": len(dna.seq),
                                "topology": "circular",
                                "mCherry_coordinates": [
                                    start,
                                    start + len(replacement),
                                ],
                                "mCherry_length": len(replacement),
                                "sequence_and_flanks_verified": True,
                                "inputs_unchanged": True,
                                "png_dimensions": [width, height],
                                "EcoRI": sites,
                            }
                        )
                        opened = await call("snapgene_open", workflow_id=workflow_id)
                        require(
                            opened["opened"] == converted["construct"],
                            "Opened ref differs from converted ref.",
                        )
                        report.update({"status": "passed", "opened": opened["opened"]})
                    finally:
                        if workflow_id:
                            status = await call(
                                "workflow_status", workflow_id=workflow_id
                            )
                            (folder / "workflow_status.json").write_text(
                                json.dumps(status, indent=2) + "\n", encoding="utf-8"
                            )
    except Exception as error:
        report.update({"status": "failed", "failure": str(error)})
        raise
    finally:
        (folder / "mcp_calls.json").write_text(
            json.dumps(calls, indent=2) + "\n", encoding="utf-8"
        )
        (folder / "verification.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-prefix",
        help="Workspace-relative output base, e.g. outputs/pEGFP-N1-mCherry. Existing files are never overwritten.",
    )
    options = parser.parse_args()
    asyncio.run(run(options.output_prefix))
