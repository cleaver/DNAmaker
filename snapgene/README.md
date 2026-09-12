# SnapGene integration (Person 1)

Windows desktop adapter for `agent.adapters.SnapGeneService`. Tested with
SnapGene 8.2.2. Python 3.11+; no additional runtime Python dependencies.
Run the MCP backend on the Windows computer with an activated SnapGene install.

## Agent integration

From the repository root, in PowerShell:

```powershell
$env:DNA_MAKER_SNAPGENE_ADAPTER = 'snapgene.adapter:create_service'
$env:DNA_MAKER_BIOLOGY_ADAPTER = 'dnamaker.service:create_biology_adapter'
$env:SNAPGENE_EXE = 'C:\Program Files\SnapGene\SnapGene.exe'
# Optional when launching from another directory:
$env:DNA_MAKER_WORKSPACE = (Get-Location).Path
python -m snapgene health
```

Person 3's existing `agent.bootstrap` loads this factory; keep their biology
adapter configuration and MCP launch command. Do not run a separate bridge server.

```python
from agent.models import ConstructRef
from snapgene import create_service

service = create_service()
# Caller has validated this exact construct through BiologyService.
dna = service.convert(
    ConstructRef('artifacts/validated-result.gb', 'genbank', 'pExample'),
    output_path='artifacts/result.dna',
)
service.open(dna)  # returns None only after a matching document window appears
```

`convert` returns the shared `ConstructRef`, with `format='snapgene'`. Paths are
returned relative to the workspace. Inputs and outputs must stay inside it.
Failures raise `agent.errors.WorkflowError(code, message, details)`; the existing
MCP layer handles JSON serialization. No `{ok: ...}` wrapper is returned by the
Python adapter methods.

## Operation order and limitations

1. Read, modify and validate with the biology/agent components.
2. Convert to a fresh `.dna` path.
3. Optionally render the `.dna` map.
4. Open the returned `.dna` reference **last**.

SnapGene's CLI requires its GUI to be closed. The adapter returns `snapgene_busy`
if SnapGene is running; it never closes or kills the user's existing session.
Save your work and exit SnapGene normally before another conversion/render run.
Jobs are serialized across threads and processes in the same workspace. Use one
workspace/backend per desktop. An external/manual app launch can still race a job.

CLI output is verified in a temporary directory before publication. Existing
destinations are never overwritten. A failed operation can leave an empty output
directory but does not publish an unverified output. GenBank `.gbk` and FASTA
`.fa` normalization is handled while retaining the caller's requested output path.
Artifact header checks are not biological validation; round-trip verification
of the demo fixtures is covered by the live tests.

Opening is verified by a visible SnapGene window title matching the filename.
It does not prove biological correctness or distinguish another open file with
the same basename. Use unique output basenames. Modal/license dialogs are never
dismissed automatically; an unconfirmed open reports observed window titles.
No automatic retries for GUI actions. Resolve a busy app/dialog before retrying.

## Additional local utilities

`export` is a local utility. `render_map` is now part of the shared contract and
is exposed by the workflow manager through `snapgene_render`:

```python
gb = service.export(source_dna, output_path='artifacts/input.gb', output_format='genbank')
fa = service.export(source_dna, output_path='artifacts/input.fasta', output_format='fasta')
png_path = service.render_map(dna, output_path='artifacts/result.png')
```

FASTA is sequence-only and cannot preserve features. Use GenBank for team handoffs.
JSON inputs must be serialized to GenBank by the biology component. Rendering
uses SnapGene's real `--createPreview` command and returns a PNG path, not a mock
or screenshot. Maps reflect SnapGene's saved display settings.

Local fixture/diagnostic commands (these do not perform workflow validation):

```powershell
python -m snapgene export snapgene-demo-files/backbones/pEGFP-N1.dna artifacts/demo/pEGFP-N1.gb
python -m snapgene convert artifacts/demo/pEGFP-N1.gb artifacts/demo/pEGFP-N1-copy.dna
python -m snapgene render artifacts/demo/pEGFP-N1-copy.dna artifacts/demo/pEGFP-N1.png
python -m snapgene open artifacts/demo/pEGFP-N1-copy.dna
```

Use new output paths on reruns. The diagnostic CLI prints JSON and exits with
status 1 on a handled error. It is for trusted local use, not an agent validation gate.

## Verification

### Complete Windows vertical slice

Close SnapGene normally, then run from the repository root:

```powershell
uv sync --frozen
.venv/Scripts/python -m snapgene.vertical_slice
```

The runner loads the real biology and SnapGene factories through the existing
bootstrap. It reads `inputs/pEGFP-N1.gb`, adds a `misc_feature` annotation named
`MVP integration verified` at `[590, 671)` on strand `1`, validates, saves GenBank,
converts to `.dna`, renders PNG, and opens the exact converted artifact last.
Because `save_construct` does not update the current reference, the runner reads
and revalidates the saved GenBank before conversion. No validation gate is bypassed.

Each run creates `artifacts/vertical-slice-<timestamp>-<id>/` containing the
GenBank, SnapGene, PNG, an independent round-trip GenBank check,
`workflow_status.json`, and `verification.json`. Verification checks the unchanged
source hash, unchanged sequence, added annotation, preserved topology, feature
types/locations/labels, and PNG dimensions. Use `--no-open` for an artifact-only run.

Verified on September 12, 2026 with SnapGene 8.2.2: all steps passed; 4,733 bp,
circular, 14 features, 1,073 × 934 PNG. This is an **annotation mutation** vertical
slice, not a sequence replacement or Gibson simulation. The latest biology adapter
also supports the fixture's adjacent joined EGFP segments; see the real MCP run below.

### Real MCP server with both adapters

Close SnapGene normally, then run:

```powershell
.venv/Scripts/python -m snapgene.mcp_vertical_slice
```

To use the acceptance request's exact filenames:

```powershell
.venv/Scripts/python -m snapgene.mcp_vertical_slice --output-prefix outputs/pEGFP-N1-mCherry
```

This creates `outputs/pEGFP-N1-mCherry.gb`, `.dna`, and `.png`. The runner rejects
existing output files; choose another prefix for subsequent runs. Diagnostic
logs remain in a unique `artifacts/mcp-live-.../` directory.

This launches `python -m agent.server` as a real stdio MCP subprocess configured
with `dnamaker.service:create_biology_adapter` and `snapgene.adapter:create_service`.
It inspects both `inputs/pEGFP-N1.gb` and `inputs/mCherry.gb` through MCP, replaces
the EGFP region using the donor CDS, scans EcoRI, validates, saves GenBank,
reloads and revalidates that file, converts, renders, and opens via MCP tools.
It independently reads the saved GenBank and `.dna` to check sequence/flanks,
mCherry coordinates and orientation, circular topology, unchanged input hashes,
and the exported PNG signature/dimensions. It does not simulate Gibson assembly.

Outputs are under `artifacts/mcp-live-<timestamp>-<id>/`: `.gb`, `.dna`, `.png`,
`mcp_calls.json`, `workflow_status.json`, `verification.json`, and `server.stderr.log`.
The MCP server process is stopped after the test; the SnapGene document stays open.

Verified against main `f08d60f` on September 12, 2026: real MCP replacement,
conversion, rendering, and opening passed without adapter errors. Result: 4,724 bp,
circular; mCherry `[678, 1389)` on strand `1`; PNG 1,121 × 934.
That run reported a stale EGFP `/translation` qualifier on the replacement.
Main `77fc02a` removes inherited translation and other outdated replacement
metadata; this updated version has not yet been live-retested on Windows.
The runner checks for stale metadata and reports warnings; it does not certify
biological completeness. The handoff procedure is documented in
[`docs/person2/HANDOFF.md`](../docs/person2/HANDOFF.md).
The installed MCP/Pydantic combination also emits a non-blocking `lifespan`
forward-reference warning at startup, retained in the stderr log.

### Component tests

```powershell
python -m unittest discover -s tests -v
# Real SnapGene test: close SnapGene first. Creates unique artifact directories.
$env:DNA_MAKER_LIVE_SNAPGENE = '1'
# Optional: verifies opening and leaves the final plasmid visible.
$env:DNA_MAKER_LIVE_OPEN = '1'
python -m unittest discover -s tests -p test_snapgene_live.py -v
```

The live test exports pEGFP-N1 and mCherry, converts them back to `.dna`, re-exports
GenBank, and compares sequence, topology and feature blocks (ignoring standalone
display-color notes and trailing whitespace added/normalized by SnapGene). It also
checks FASTA sequence, PNG dimensions, and unchanged source hashes. This verifies
file interchange, not EGFP replacement or Gibson assembly.

## Handoff to teammates

- Person 2: use the exported GenBank fixtures; provide a validated GenBank result.
  Do sequence edits and 0-based/end-exclusive coordinate handling in biology.
- Person 3: factory is ready. The current workflow manager enforces validation
  and converted-artifact provenance before rendering/opening. Use
  `snapgene_convert`, `snapgene_render`, then `snapgene_open` in that order.
  The successful vertical slice exercises these real methods and retains their
  JSON-serializable workflow log. Conversion does not update `current_construct`.
- PCR, Gibson/Golden Gate GUI workflows and sequence editing are deferred by the
  agreed MVP plan. There are no placeholder methods claiming these operations work.

## References

- [SnapGene CLI conversion](https://support.snapgene.com/hc/en-us/articles/10384393330836-Command-Line-Converting-File-Formats)
- [SnapGene CLI maps](https://support.snapgene.com/hc/en-us/articles/10384408885268-Command-Line-Creating-Maps-of-DNA-Sequences)
- [Shared contract](../CONTRACT.md)
