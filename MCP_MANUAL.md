# DNA Maker MCP Manual

This manual explains how to install, configure, use, test, and extend the DNA
Maker MCP server. It is written for people who did not build the project.

## 1. What this tool is

DNA Maker is a small orchestration layer around two independent components:

1. A biology adapter that reads and writes sequence files and performs sequence
   operations.
2. A SnapGene adapter that converts files, renders maps, and controls the
   SnapGene desktop application.

The MCP server exposes these capabilities as typed tools over the Model Context
Protocol (MCP). A workflow has an in-memory session and a JSON-serializable
operation log.

The MCP server does **not** require AI to perform an operation. MCP is a tool
protocol, not an AI model. There are two ways to use this project:

- **AI-assisted:** Codex or another MCP-compatible model interprets a natural-
  language request and calls the tools in the correct order.
- **Deterministic/manual:** a human or program uses an MCP client and calls the
  tools directly. The biology and SnapGene adapters can also be called from
  Python without an AI model.

The current server does not contain its own language model or autonomous
planner. Natural-language planning is supplied by the MCP host. The server
enforces the important state and validation rules regardless of which client
calls it.

## 2. MVP scope

The implemented MVP supports:

- reading GenBank, FASTA, and structured JSON constructs through the biology
  adapter;
- exact feature-targeted sequence replacement;
- adding annotations;
- restriction-site analysis;
- construct validation;
- saving GenBank, FASTA, or JSON artifacts;
- converting a validated GenBank artifact to SnapGene format;
- rendering a SnapGene map;
- opening the exact converted SnapGene artifact;
- a reproducible workflow status and operation log.

The following are deliberately not implemented in the current MCP surface:

- primer design;
- PCR simulation;
- Gibson, Golden Gate, or restriction-cloning design;
- ORF/translation tools as agent tools;
- SnapGene GUI cloning workflows;
- durable workflow storage or multi-user state;
- a web UI;
- an internal LLM agent loop.

Do not describe these deferred capabilities as available merely because they
appear in the long-term project README.

## 3. Architecture

```text
Codex or another MCP client
        │  stdio MCP requests
        ▼
agent.server (FastMCP)
        │
        ▼
WorkflowManager
  ├── in-memory session state
  ├── validation/provenance gates
  └── operation log
        │
        ├── BiologyService adapter
        │     └── src/dnamaker/service.py
        │
        └── SnapGeneService adapter
              └── snapgene/adapter.py
```

The process entry point is `agent.server:main`. It runs an MCP stdio server;
it does not expose an HTTP port. The `dna-maker-mcp` console command and
`python -m agent.server` start the same server.

The biology and SnapGene implementations are selected at process startup from
environment variables. This keeps the agent layer independent of either
implementation.

## 4. Requirements

### All platforms

- Python 3.11 or newer;
- this repository;
- a writable workspace directory;
- project dependencies installed in a virtual environment.

Homebrew Python 3.14 works. A virtual environment is still recommended so the
project does not modify the system Python installation.

### SnapGene-specific work

- Windows;
- an installed and licensed SnapGene desktop application;
- permission to launch SnapGene and inspect its visible document windows.

The current SnapGene adapter intentionally reports
`snapgene_platform_unsupported` on macOS and Linux. Biology work and all fake-
SnapGene tests can run there.

## 5. Installation

### macOS/Linux

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Activate the environment if desired:

```bash
source .venv/bin/activate
```

### Windows PowerShell

From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

The package installs the MCP runtime, Biopython, and Pydantic dependencies.

## 6. Adapter configuration

The MCP process reads these variables when `main()` starts:

| Variable | Required | Meaning |
|---|---:|---|
| `DNA_MAKER_WORKSPACE` | no | Root directory for relative construct/artifact paths. Defaults to the process working directory. |
| `DNA_MAKER_BIOLOGY_ADAPTER` | yes for biology calls | `module:factory` reference returning a `BiologyService`. |
| `DNA_MAKER_SNAPGENE_ADAPTER` | yes for SnapGene calls | `module:factory` reference returning a `SnapGeneService`. |
| `DNA_MAKER_BIOLOGY_ARTIFACT_DIR` | no | Relative or absolute directory for unique biology mutation artifacts. |
| `SNAPGENE_EXE` | Windows optional | Full path to `SnapGene.exe`; otherwise the adapter uses the standard Program Files location. |

The production values are:

```text
DNA_MAKER_BIOLOGY_ADAPTER=dnamaker.service:create_biology_adapter
DNA_MAKER_SNAPGENE_ADAPTER=snapgene.adapter:create_service
```

`module:factory` means that Python imports `module`, looks up `factory`, and
calls it with no arguments. For example,
`dnamaker.service:create_biology_adapter` imports
`dnamaker.service` and calls `create_biology_adapter()`.

If either variable is missing or invalid, the server still starts so that MCP
initialization can succeed. Calls that need the missing component return an
explicit `biology_unavailable` or `snapgene_unavailable` error.

### macOS/Linux environment example

```bash
export DNA_MAKER_WORKSPACE="$PWD"
export DNA_MAKER_BIOLOGY_ADAPTER='dnamaker.service:create_biology_adapter'
export DNA_MAKER_SNAPGENE_ADAPTER='snapgene.adapter:create_service'
```

The biology adapter will work with this configuration. SnapGene calls will
remain unavailable on a non-Windows host.

### Windows PowerShell environment example

```powershell
$env:DNA_MAKER_WORKSPACE = (Get-Location).Path
$env:DNA_MAKER_BIOLOGY_ADAPTER = 'dnamaker.service:create_biology_adapter'
$env:DNA_MAKER_SNAPGENE_ADAPTER = 'snapgene.adapter:create_service'
$env:SNAPGENE_EXE = 'C:\Program Files\SnapGene\SnapGene.exe'
```

Keep the workspace the same for the biology and SnapGene adapters. Both use
workspace-relative artifact paths.

## 7. Connecting the server to Codex

Configure a **local stdio MCP server** in the Codex MCP settings with:

- working directory: the repository root;
- command on macOS/Linux: `.venv/bin/python`;
- command on Windows: `.venv\Scripts\python.exe`;
- arguments: `-m agent.server`;
- the adapter environment variables from the previous section.

The equivalent launch commands are:

```bash
.venv/bin/python -m agent.server
```

```powershell
.\.venv\Scripts\python.exe -m agent.server
```

The process waits for MCP messages on standard input and writes protocol
messages to standard output. A manually launched server may appear idle; that
is normal. Prefer letting Codex start and stop it as an MCP child process.

Do not run a second SnapGene bridge. The MCP server loads
`snapgene.adapter:create_service` directly in the same process.

The recommended Codex operating policy is in
`agent/prompts/codex_instructions.md`. It tells the host model to inspect,
execute, validate, export, and open in that order.

## 8. Running without AI

An MCP client can call the same server methods without a language model. The
client must:

1. initialize an MCP session;
2. call `start_workflow` and retain the returned `workflow_id`;
3. pass that ID to every later tool call;
4. inspect each `{ok: ...}` response before making the next dependent call.

For a Python embedding or unit test, use `WorkflowManager` directly:

```python
from agent.session import WorkflowManager
from dnamaker.service import create_biology_adapter

biology = create_biology_adapter()
manager = WorkflowManager(biology, snapgene_service)
workflow = manager.start("Replace EGFP with mCherry")
```

Direct adapter calls return Python dataclasses or raise exceptions. The MCP
server is the layer that wraps successful results in `{\"ok\": true, ...}` and
translates exceptions into structured error objects.

## 9. Construct data model

### ConstructRef

```json
{
  "path": "inputs/pEGFP-N1.gb",
  "format": "genbank",
  "name": "pEGFP-N1"
}
```

`format` can be `genbank`, `fasta`, `json`, or `snapgene` in the shared
reference type. The biology adapter accepts GenBank, FASTA, and JSON; it
rejects SnapGene inputs. SnapGene conversion accepts a validated GenBank
reference through the workflow manager.

Paths are workspace-relative in the contract. Do not use `..` to escape the
workspace. Absolute paths are accepted by the biology implementation only when
they resolve inside the configured workspace.

### ConstructSummary

`read_construct` returns:

```json
{
  "construct": {
    "path": "inputs/pEGFP-N1.gb",
    "format": "genbank",
    "name": "pEGFP-N1"
  },
  "sequence_length": 4733,
  "topology": "circular",
  "features": []
}
```

Each feature summary contains at least `name`, `type`, `start`, `end`,
`strand`, and `qualifiers`. Compound features may also contain `parts`.

`read_construct` is intentionally a summary operation; it does not return the
entire DNA string. A caller that needs donor sequence text must read the donor
artifact using its own file/biology layer. The repository's
`dnamaker.handoff` helper demonstrates this for `mCherry.gb`.

### Coordinates

All agent and biology coordinates use **0-based, end-exclusive** intervals:

```text
[start, end)
```

For example, `start=10, end=14` covers four bases at positions 10, 11, 12,
and 13. GenBank's 1-based inclusive notation is converted only at the I/O
boundary.

`strand` must be `1` or `-1`.

### ValidationResult

```json
{
  "valid": true,
  "checks": [
    {"name": "sequence_alphabet", "passed": true},
    {"name": "topology", "passed": true},
    {"name": "feature_bounds", "passed": true},
    {"name": "feature_strands", "passed": true}
  ]
}
```

Every check has a stable `name` and a Boolean `passed` field. Optional details
must be JSON serializable.

## 10. Workflow state and mandatory order

Every workflow begins with `start_workflow`:

```text
start_workflow(request)
        ↓ workflow_id
read_construct(workflow_id, ...)
        ↓
zero or more read-only analyses and mutations
        ↓
validate_construct(workflow_id)
        ↓ valid=true
save_construct / snapgene_convert
        ↓ converted ConstructRef
snapgene_render and/or snapgene_open
```

The following rules are enforced by `WorkflowManager`:

- `read_construct` must occur before biology operations;
- sequence and annotation mutations execute immediately—there is no approval
  prompt in this MVP;
- every mutation invalidates previous validation and any converted/map artifact;
- saving requires successful validation of the current exact `ConstructRef`;
- SnapGene conversion requires successful validation and a GenBank current
  reference;
- rendering requires conversion in the same workflow;
- opening requires the exact `ConstructRef` returned by conversion in the same
  workflow;
- `workflow_status` returns the session state and successful operation log.

Validation is tied to the full `ConstructRef`, not merely a filename. This
prevents a result from one artifact version being silently used for another.

### Important save behavior

`save_construct` writes a new caller-selected artifact and returns its
`ConstructRef`, but it does not replace `current_construct` in the session.
When the saved file is the intended SnapGene input, reload and validate that
returned reference before converting it:

```text
save_construct → read_construct(saved_ref) → validate_construct → snapgene_convert
```

The `dnamaker.handoff` helper follows this exact pattern.

## 11. MCP tool reference

All tools return one of these envelopes:

```json
{"ok": true, "result": {}}
```

```json
{
  "ok": false,
  "error": {
    "code": "validation_required",
    "message": "Validate the current construct successfully before saving or using SnapGene.",
    "details": {}
  }
}
```

### `start_workflow`

Creates an in-memory workflow session.

Input:

```json
{"request": "Replace EGFP with mCherry and open the result."}
```

The result contains a UUID `workflow_id`. Keep it for every subsequent call.
An empty request returns `invalid_request`.

### `workflow_status`

Returns the current request, current construct, validation/provenance state,
converted SnapGene reference, map path, and successful operation records.

Input:

```json
{"workflow_id": "..."}
```

State is process-local and disappears when the MCP process exits.

### `read_construct`

Reads and summarizes a construct.

Input:

```json
{
  "workflow_id": "...",
  "path": "inputs/pEGFP-N1.gb",
  "format": "genbank",
  "name": null
}
```

`format` defaults to `genbank`; accepted biology inputs are `genbank`,
`fasta`, and `json`. The adapter normalizes the returned reference, including
the construct name. Reading a new construct resets validation and SnapGene
provenance for the workflow.

### `replace_region`

Replaces exactly one named feature and returns a new GenBank artifact.

Input:

```json
{
  "workflow_id": "...",
  "target": "EGFP",
  "replacement_sequence": "ATGC...",
  "replacement_name": "mCherry"
}
```

Target matching is exact and case-sensitive. Zero matches and multiple matches
are errors. If `replacement_name` is omitted/null, the target feature is
removed and no replacement annotation is created. If it is provided, the
replacement keeps the target feature type and receives that label.

Features wholly downstream shift by the sequence length delta. Unsafe partial
overlaps are rejected. Adjacent joined segments, such as the EGFP annotation
exported in `inputs/pEGFP-N1.gb`, are treated as one interval. Genuine gaps and
origin-spanning target locations remain unsupported in the MVP.

This is a destructive workflow operation and immediately invalidates prior
validation. It does not overwrite the input; the biology adapter creates a
unique artifact below its biology artifact directory.

### `add_annotation`

Adds a feature and returns a new GenBank artifact.

Input:

```json
{
  "workflow_id": "...",
  "name": "CMV",
  "feature_type": "promoter",
  "start": 364,
  "end": 568,
  "strand": 1
}
```

The interval must satisfy `0 <= start < end <= sequence_length`; strand must
be `1` or `-1`. Overlap with existing annotations is allowed. The operation
invalidates prior validation.

### `find_restriction_sites`

Performs read-only restriction-site analysis on the current construct.

Input:

```json
{"workflow_id": "...", "enzyme": "EcoRI"}
```

The result contains the current construct, enzyme, and a sorted `sites` list.
Each site has at least:

```json
{"position": 628, "strand": 1, "site": "GAATTC"}
```

Positions are 0-based starts in the stored forward sequence. Circular
origin-crossing recognition sites are normalized to their start position.

### `validate_construct`

Validates the current construct and returns `ValidationResult`.

Input:

```json
{"workflow_id": "..."}
```

A true result authorizes save and SnapGene actions for the exact current
reference. A false result is a normal result, not a transport failure; do not
continue to export. A fresh validation clears older SnapGene conversion/map
state, so convert again after validating again.

### `save_construct`

Writes the current validated construct to a caller-selected path.

Input:

```json
{
  "workflow_id": "...",
  "output_path": "outputs/result.gb",
  "output_format": "genbank"
}
```

Biology output formats are `genbank`, `fasta`, and `json`. Use GenBank when
annotations must be preserved. Follow the save behavior described above if the
saved copy will be sent to SnapGene.

### `snapgene_convert`

Converts the current validated GenBank artifact to a new SnapGene artifact.

Input:

```json
{
  "workflow_id": "...",
  "output_path": "outputs/result.dna"
}
```

The result is a `ConstructRef` with `format: "snapgene"`. The reference is
stored in the session and is the only reference accepted by later map/open
operations. The adapter owns file verification and refuses existing output
paths.

### `snapgene_render`

Renders a PNG map for the SnapGene reference returned by
`snapgene_convert`.

Input:

```json
{
  "workflow_id": "...",
  "output_path": "outputs/result.png",
  "size": 1200
}
```

`size` defaults to 1200 and the SnapGene adapter accepts 100–4096 pixels. The
result contains the converted construct reference, `map_path`, and size.

### `snapgene_open`

Opens the exact converted reference in SnapGene. Call it last.

Input using the stored converted reference:

```json
{"workflow_id": "..."}
```

The optional explicit form is only valid when it exactly matches the returned
reference:

```json
{
  "workflow_id": "...",
  "path": "outputs/result.dna",
  "format": "snapgene"
}
```

Opening an arbitrary `.dna` path returns `snapgene_conversion_required` or
`snapgene_reference_mismatch`. The adapter confirms a visible document window;
it does not dismiss dialogs or terminate SnapGene.

## 12. Complete example with the repository inputs

The repository contains:

- `inputs/pEGFP-N1.gb`: 4733 bp, circular vector;
- `inputs/mCherry.gb`: 711 bp, linear donor CDS.

The expected replacement removes the 720 bp EGFP region and inserts the 711 bp
mCherry CDS, resulting in a 4724 bp circular construct.

### AI-assisted request

In Codex, after configuring the MCP server, ask:

> Use `inputs/pEGFP-N1.gb` as the vector and the mCherry CDS from
> `inputs/mCherry.gb` as the replacement for the exact `EGFP` feature. Label
> the replacement `mCherry`, scan for EcoRI sites, validate the construct,
> save it as `outputs/pEGFP-N1-mCherry.gb`, convert it to
> `outputs/pEGFP-N1-mCherry.dna`, render
> `outputs/pEGFP-N1-mCherry.png`, and open the converted file last.

The current `replace_region` tool accepts replacement sequence text. The host
must read/extract the donor sequence before calling it; it must not guess or
truncate the sequence.

### Deterministic tool sequence

The same run, expressed as tool actions, is:

```text
1. start_workflow(request)
2. read_construct(workflow_id, "inputs/pEGFP-N1.gb", "genbank")
3. obtain the exact mCherry CDS sequence from inputs/mCherry.gb
4. replace_region(workflow_id, target="EGFP", replacement_sequence=..., replacement_name="mCherry")
5. find_restriction_sites(workflow_id, enzyme="EcoRI")
6. validate_construct(workflow_id)
7. save_construct(workflow_id, "outputs/pEGFP-N1-mCherry.gb", "genbank")
8. read_construct(workflow_id, saved ConstructRef)
9. validate_construct(workflow_id)
10. snapgene_convert(workflow_id, "outputs/pEGFP-N1-mCherry.dna")
11. snapgene_render(workflow_id, "outputs/pEGFP-N1-mCherry.png")
12. snapgene_open(workflow_id)
13. workflow_status(workflow_id)
```

The extra read/validate after saving is intentional: it validates the exact
GenBank file that will be passed to SnapGene.

### Biology-only handoff helper

To prepare and validate the real GenBank result without SnapGene, run:

```bash
.venv/bin/python -m dnamaker.handoff --workspace .
```

This creates a unique artifact directory under `artifacts/biology/`, preserves
input SHA-256 hashes, checks the donor CDS translation, performs the EGFP to
mCherry replacement, scans EcoRI, validates the output, reloads and validates
the saved GenBank reference, and writes `handoff.json`. SnapGene conversion is
left pending for the Windows handoff.

## 13. SnapGene Windows runbook

Run these steps on the Windows computer that has SnapGene installed.

### Prepare

```powershell
cd <repo-path>
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e .

$env:DNA_MAKER_WORKSPACE = (Get-Location).Path
$env:DNA_MAKER_BIOLOGY_ADAPTER = 'dnamaker.service:create_biology_adapter'
$env:DNA_MAKER_SNAPGENE_ADAPTER = 'snapgene.adapter:create_service'
$env:SNAPGENE_EXE = 'C:\Program Files\SnapGene\SnapGene.exe'
```

Confirm that `inputs/pEGFP-N1.gb` and `inputs/mCherry.gb` are present. Use a
workspace path that contains all inputs and generated artifacts.

### Check installation

Close SnapGene and run:

```powershell
.\.venv\Scripts\python -m snapgene health
```

The result should report `available: true`. The adapter does not close or kill
an existing SnapGene process.

### Run the verified vertical-slice utility

The repository includes a deterministic annotation-only conversion check:

```powershell
.\.venv\Scripts\python -m snapgene.vertical_slice --no-open
```

It creates unique artifacts under `artifacts/vertical-slice-*`, validates and
reloads GenBank, converts to `.dna`, renders a PNG, performs an independent
GenBank round-trip check, compares feature locations/labels, checks the PNG
header/dimensions, and writes `workflow_status.json` and `verification.json`.

Once the no-open run succeeds, run the same command without `--no-open` to
verify the final visible SnapGene window:

```powershell
.\.venv\Scripts\python -m snapgene.vertical_slice
```

### Run the MCP workflow

Start the MCP server through Codex using the configured environment. Execute
the complete request from section 12. The required order is:

```text
read → replace/analyze → validate → save GenBank → reload/validate
→ convert .dna → render PNG → open
```

Close SnapGene before conversion and map rendering. Open the converted `.dna`
last. Use unique output basenames and do not reuse an existing output path.

### Optional live tests

The opt-in live tests exercise `.dna`/GenBank interchange and, optionally,
opening:

```powershell
$env:DNA_MAKER_LIVE_SNAPGENE = '1'
$env:DNA_MAKER_LIVE_OPEN = '1'
.\.venv\Scripts\python -m pytest tests/test_snapgene_live.py -v
```

Close SnapGene before conversion/render portions. The live tests are not a
replacement for the agent workflow acceptance run; they verify the desktop
adapter and format round-trip independently.

## 14. Testing on any platform

Run the full non-live suite from the repository root:

```bash
.venv/bin/python -m pytest -q
```

On Windows:

```powershell
.\.venv\Scripts\python -m pytest -q
```

The suite includes:

- biology parser, mutation, restriction, validation, and round-trip tests;
- real `pEGFP-N1.gb`/`mCherry.gb` handoff tests;
- workflow validation/provenance tests;
- MCP stdio protocol tests using a fake SnapGene adapter;
- SnapGene adapter unit tests that do not require Windows;
- opt-in live SnapGene tests, skipped unless explicitly enabled.

The MCP stdio test starts a real server subprocess, initializes an MCP client,
lists the tools, calls the real biology adapter with the repository inputs,
checks structured errors, converts/renders/opens using a fake SnapGene service,
and inspects the workflow log.

## 15. Error handling and recovery

The MCP layer preserves stable adapter error codes. Common errors include:

| Code | Meaning | Recovery |
|---|---|---|
| `invalid_request` | Empty workflow request | Supply a nonempty request. |
| `workflow_not_found` | Unknown or expired in-memory workflow ID | Start a new workflow. |
| `construct_not_loaded` | Biology operation called before reading a construct | Call `read_construct`. |
| `target_not_found` | Exact feature name was not found | Inspect `read_construct` features and use the exact name. |
| `target_ambiguous` | More than one feature has the target name | Supply a uniquely identified target; fuzzy matching is not performed. |
| `overlapping_feature` | Mutation would move/remove another annotation ambiguously | Choose a safe target or revise the edit. |
| `unsupported_location` | Target has a gap or origin-spanning location | Use a supported single/contiguous feature. |
| `invalid_feature_location` | Annotation coordinates are outside the sequence | Recalculate 0-based end-exclusive coordinates. |
| `invalid_strand` | Strand is not `1` or `-1` | Correct the strand. |
| `validation_required` | Current reference has not passed validation | Validate the current construct. |
| `genbank_required` | SnapGene conversion was requested for a non-GenBank current reference | Save/reload a GenBank artifact, validate it, then convert. |
| `snapgene_conversion_required` | Render/open was requested before conversion | Call `snapgene_convert` in the same workflow. |
| `snapgene_reference_mismatch` | Open path does not match the converted reference | Use the reference returned by `snapgene_convert`, or omit `path`. |
| `biology_unavailable` | Biology factory was not configured | Set `DNA_MAKER_BIOLOGY_ADAPTER` and restart the server. |
| `snapgene_unavailable` | SnapGene factory was not configured | Set `DNA_MAKER_SNAPGENE_ADAPTER` and restart the server. |
| `snapgene_platform_unsupported` | SnapGene call is running outside Windows | Run SnapGene operations on Windows. |
| `snapgene_not_found` | `SnapGene.exe` was not found | Set `SNAPGENE_EXE` to the installed executable. |
| `snapgene_busy` | Another operation is active or SnapGene must be closed | Close SnapGene for CLI work and retry after the active job ends. |
| `snapgene_output_exists` | Destination already exists | Select a unique output path. |
| `snapgene_timeout` | SnapGene exceeded the configured timeout | Inspect SnapGene/dialogs and retry deliberately. |
| `adapter_error` | An unexpected adapter exception had no stable code | Inspect the message and adapter logs/code. |

Failed dependent calls should stop the workflow. Successful calls remain in
the operation log; a failure returned before an operation completes is not
recorded as a successful operation.

## 16. File and side-effect rules

- Biology mutation artifacts are unique files below the biology artifact
  directory and do not overwrite their input.
- Save destinations are caller-selected; use unique paths and do not assume a
  save updates the workflow's current reference.
- SnapGene conversion and map rendering stage and verify outputs before
  publishing them. Existing SnapGene destinations are refused.
- SnapGene CLI conversion/render jobs require the desktop application to be
  closed. The adapter never kills the application.
- SnapGene opening is intentionally last and waits for a matching visible
  document window. It does not dismiss license or modal dialogs.
- The workflow session is in memory only. Restarting the server loses the
  workflow ID and operation history, but does not remove artifacts already
  written to disk.
- The MCP server uses stdio. Do not print diagnostic messages to stdout from an
  adapter; stdout is the protocol channel. Use stderr or structured errors.

## 17. Implementing or replacing an adapter

The authoritative shared interfaces are in `agent/adapters.py` and
`CONTRACT.md`.

### Biology adapter

Provide these methods:

```python
read_construct(construct: ConstructRef) -> ConstructSummary
replace_region(construct, *, target, replacement_sequence, replacement_name) -> ConstructRef
add_annotation(construct, *, name, feature_type, start, end, strand) -> ConstructRef
find_restriction_sites(construct, *, enzyme) -> list[dict]
validate_construct(construct) -> ValidationResult
save_construct(construct, *, output_path, output_format) -> ConstructRef
```

Provide a zero-argument factory and set
`DNA_MAKER_BIOLOGY_ADAPTER=your_module:create_service`.

Biology exceptions should expose `code`, `message`, and optional `details`.
They should remain ordinary Python exceptions; the MCP layer translates them.

### SnapGene adapter

Provide:

```python
convert(construct: ConstructRef, *, output_path: str) -> ConstructRef
render_map(construct: ConstructRef, *, output_path: str, size: int = 1200) -> str
open(construct: ConstructRef) -> None
```

`convert` must return a new `ConstructRef` with `format="snapgene"`.
`render_map` returns a workspace-relative PNG path. `open` returns only after
the requested desktop document is confirmed, or raises a structured error.

Adapters must not call each other. The workflow manager owns ordering and
validation gates.

### Custom bootstrap example

```python
from agent.bootstrap import manager_from_environment

manager = manager_from_environment()
```

For tests, inject fake services directly:

```python
from agent.session import WorkflowManager

manager = WorkflowManager(fake_biology, fake_snapgene)
```

## 18. Adding a new MCP tool

Use this sequence for a future operation:

1. Define its input/output semantics in `CONTRACT.md`.
2. Add or extend the relevant adapter protocol only if the operation belongs
   to that component.
3. Add a `WorkflowManager` method with the necessary state/validation gate.
4. Add a `@mcp.tool()` wrapper in `agent/server.py` that calls `_run`.
5. Record successful calls in `OperationRecord`.
6. Add a direct manager test.
7. Add an MCP stdio test if the operation changes the public tool surface.
8. Update `agent/prompts/codex_instructions.md` so the host model knows when
   to use it.
9. Document platform and side-effect requirements here.

Do not add an apparently useful tool without defining its artifact ownership,
coordinate rules, validation behavior, and error contract first.

## 19. Quick reference

```text
Install:
  python3 -m venv .venv
  .venv/bin/python -m pip install -e .

Run server:
  .venv/bin/python -m agent.server

Run tests:
  .venv/bin/python -m pytest -q

Prepare biology-only handoff:
  .venv/bin/python -m dnamaker.handoff --workspace .

Check SnapGene on Windows:
  python -m snapgene health

Run verified SnapGene vertical slice:
  python -m snapgene.vertical_slice --no-open
  python -m snapgene.vertical_slice
```

The short shared contract is in `CONTRACT.md`; the SnapGene-specific Windows
runbook is in `snapgene/README.md`; the Codex operating policy is in
`agent/prompts/codex_instructions.md`.
