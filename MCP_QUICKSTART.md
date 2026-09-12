# DNA Maker MCP Quick Start

This is the short usage guide. For the complete reference, see
[`MCP_MANUAL.md`](MCP_MANUAL.md).

## 1. Install

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

On Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

## 2. Configure adapters

Set these variables before Codex starts the MCP server:

```text
DNA_MAKER_WORKSPACE=<repository path>
DNA_MAKER_BIOLOGY_ADAPTER=dnamaker.service:create_biology_adapter
DNA_MAKER_SNAPGENE_ADAPTER=snapgene.adapter:create_service
```

On Windows, also set:

```text
SNAPGENE_EXE=C:\Program Files\SnapGene\SnapGene.exe
```

Configure Codex to run this local stdio server from the repository root:

```text
.venv/bin/python -m agent.server          # macOS/Linux
.venv\Scripts\python.exe -m agent.server # Windows
```

The biology tools work on any supported platform. SnapGene conversion, map
rendering, and opening require Windows with SnapGene installed.

## 3. Use it with Codex

Give Codex a request such as:

> Use `inputs/pEGFP-N1.gb` as the vector and replace the `EGFP` feature with
> the mCherry CDS from `inputs/mCherry.gb`. Label it `mCherry`, validate the
> result, save it as `outputs/pEGFP-N1-mCherry.gb`, convert it to
> `outputs/pEGFP-N1-mCherry.dna`, render a map, and open the converted file
> last.

Codex will call the tools in this order:

```text
start_workflow
read_construct
modify/analyze
validate_construct
save_construct
snapgene_convert
snapgene_render (optional)
snapgene_open (last)
workflow_status
```

Mutations execute immediately. Saving and SnapGene actions require successful
validation. SnapGene opening must use the exact reference returned by
`snapgene_convert`.

## 4. Use it without AI

An MCP client or Python program can call the same tools directly. Always:

1. call `start_workflow` and keep its `workflow_id`;
2. call `read_construct` before editing;
3. pass the same ID to every tool;
4. stop when a response has `"ok": false`;
5. validate before saving or using SnapGene;
6. call `workflow_status` at the end.

Successful responses look like:

```json
{"ok": true, "result": {}}
```

Failures look like:

```json
{"ok": false, "error": {"code": "...", "message": "...", "details": {}}}
```

## 5. Useful commands

Run tests:

```bash
.venv/bin/python -m pytest -q
```

Prepare a biology-only GenBank handoff:

```bash
.venv/bin/python -m dnamaker.handoff --workspace .
```

Check SnapGene on Windows:

```powershell
.\.venv\Scripts\python -m snapgene health
```

Close SnapGene before conversion or map rendering. Open the generated `.dna`
file last. Use new output paths for each run.
