# SnapGene integration (Person 1)

Windows desktop adapter for `agent.adapters.SnapGeneService`. Tested with
SnapGene 8.2.2. Python 3.11+; no additional runtime Python dependencies.
Run the MCP backend on the Windows computer with an activated SnapGene install.

## Agent integration

From the repository root, in PowerShell:

```powershell
$env:DNA_MAKER_SNAPGENE_ADAPTER = 'snapgene.adapter:create_service'
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

These do not change the shared two-method contract:

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
- Person 3: factory is ready. Validation is enforced by the workflow manager,
  because `ConstructRef` has no validation state. At the baseline main commit
  `84dbff8`, `snapgene_open` bypasses that gate: add validation and provenance
  checks before exposing it to the agent. Pass the reference returned by
  `snapgene_convert`; conversion does not update `current_construct`.
- Map export is available locally. To expose it as an agent tool, Person 3 must
  add its tool definition, validation gate and JSON-serializable workflow log
  entry. Do not hide map creation inside `convert` or change its return shape.
- PCR, Gibson/Golden Gate GUI workflows and sequence editing are deferred by the
  agreed MVP plan. There are no placeholder methods claiming these operations work.

## References

- [SnapGene CLI conversion](https://support.snapgene.com/hc/en-us/articles/10384393330836-Command-Line-Converting-File-Formats)
- [SnapGene CLI maps](https://support.snapgene.com/hc/en-us/articles/10384408885268-Command-Line-Creating-Maps-of-DNA-Sequences)
- [Shared contract](../CONTRACT.md)
