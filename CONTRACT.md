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
`open` has no return value; it raises when SnapGene cannot complete the action.

## Orchestration rules

- `read_construct` is required before biology operations.
- Every mutation invalidates previous validation.
- A successful validation is required before saving, converting, or opening the
  current construct through SnapGene.
- `workflow_status` is the complete reproducibility log and must remain JSON
  serializable.
