# Component contract (MVP)

This is the integration boundary between the agent, biology, and SnapGene
components. Implementations may have richer internal types, but adapters must
honour this contract.

## Artifact and coordinate rules

- `ConstructRef` is `{path, format, name?}`. `format` is one of `genbank`,
  `fasta`, `snapgene`, or `json`.
- GenBank is the MVP interchange artifact. JSON is the structured tool payload.
- Feature coordinates are **0-based, end-exclusive**: `[start, end)`.
- `strand` is `1` or `-1`.
- A mutation returns a new `ConstructRef`; it must not overwrite its input.
- Adapters raise an exception for failures. The MCP layer turns it into
  `{ok: false, error: {code, message, details}}`.

## Biology adapter

`agent.adapters.BiologyService` is the authoritative Python interface. Its MVP
methods are `read_construct`, `replace_region`, `add_annotation`,
`find_restriction_sites`, `validate_construct`, and `save_construct`.

`validate_construct` returns `{valid, checks}` where every check includes at
least a stable name and pass/fail status. A false `valid` result prevents export
and SnapGene conversion, but remains in the workflow log.

## SnapGene adapter

`agent.adapters.SnapGeneService` exposes `convert` and `open`. `convert`
receives a validated `ConstructRef` and returns a new `snapgene` reference.
`render_map` receives that same converted reference and returns a workspace-
relative PNG path. `open` has no return value; it raises when SnapGene cannot
complete the action.

## Orchestration rules

- `read_construct` is required before biology operations.
- Every mutation invalidates previous validation.
- A successful validation is required before saving, converting, or opening the
  current construct through SnapGene.
- SnapGene conversion accepts only a validated GenBank `ConstructRef`.
- `snapgene_open` accepts only the exact SnapGene `ConstructRef` returned by
  `snapgene_convert` in the same workflow; it may be omitted to open that stored
  reference directly.
- `snapgene_render` accepts only that same converted reference and is required
  to run before `snapgene_open` when a map is requested.
- `workflow_status` is the complete reproducibility log and must remain JSON
  serializable.

## Gibson MVP

`BiologyService.gibson_assemble(fragments, *, overlaps, name, circular=True,
min_overlap=15)` returns a new GenBank `ConstructRef`. Fragments are ordered,
pre-oriented linear inputs; overlap lengths explicitly describe exact suffix/prefix
junctions (including last-to-first for circular products). No primer design or
assembly-efficiency prediction is performed. Every fragment must retain a non-overlap
interior. A/C/G/T only. Source features and checked junctions are retained in the
product; provenance is saved in its GenBank comment.

The workflow/MCP `gibson_assemble` operation can start from an empty workflow,
records all fragment references/settings, and resets validation and SnapGene state.
Validate before saving. `DNA_MAKER_SNAPGENE_ADAPTER` is optional for biology-only
startup; explicitly configured invalid adapters still report configuration errors.
