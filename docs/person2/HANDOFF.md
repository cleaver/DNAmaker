# Real-fixture GenBank handoff

From the repository root:

```sh
uv run python -m dnamaker.handoff
```

Each run writes a unique directory under `artifacts/biology/handoff-<id>/`:

- `pEGFP-N1-mCherry.gb`: final GenBank construct.
- `handoff.json`: exact `ConstructRef`, validation checks, source/output hashes,
  EcoRI sites and the workflow operation log.
- Intermediate GenBank mutation artifact.

Inputs are `inputs/pEGFP-N1.gb` and `inputs/mCherry.gb`; they are not modified.
Artifacts are gitignored, so regenerate on Windows or explicitly transfer the
run directory into the same relative location in the receiving workspace.

The demo replaces the complete EGFP CDS with the donor mCherry CDS. It preserves
the existing CMV promoter and other vector features. This is direct sequence
replacement, not Gibson assembly simulation. The result is 4724 bp, circular,
with mCherry at `[678, 1389)` and an EcoRI recognition site starting at 628.
Coordinates are 0-based, end-exclusive.

The four shared validation checks cover alphabet, topology, bounds and strands.
The demo additionally checks the donor's complete-CDS translation against its
annotated protein; regression tests verify the exact output sequence and feature
preservation. This does not add general biological-function validation.

## Person 1 / Person 3 integration

Configure both factories and a shared workspace as described in the root README.
Read the report's `construct` field; do not infer the UUID directory name.
Validation is workflow state, not a flag inside `ConstructRef` or a transferable
authorization in the report. In the receiving workflow:

1. `start_workflow`.
2. `read_construct` using the exact report path, format `genbank`, and name.
3. `validate_construct`; proceed only when `valid` is true.
4. `snapgene_convert` with a new `.dna` output path.
5. `snapgene_render` with a new `.png` output path.
6. `snapgene_open` using the converted artifact (or omit its optional path).

The Windows adapter requires SnapGene to be closed for CLI jobs; open the
document last. The Linux handoff command does not invoke SnapGene. A recording
adapter tests the conversion boundary; live Windows conversion and rendering
remain the final integration check.
