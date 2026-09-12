# Person 2 biology-engine contract

This file supplements the shared [component contract](../../CONTRACT.md). The
shared contract remains authoritative at the integration boundary. This file
defines the biology-specific behavior that the shared contract intentionally
leaves open.

## Hackathon decision

Person 2 will proceed against the shared interface without waiting for edits to
the root contract. The defaults in this supplement are the working agreement
for the first integrated demo. They are deliberately narrow and can be
hardened later without changing the biology implementation's internal model.

## Alignment with the shared contract

Person 2 will provide an implementation of `agent.adapters.BiologyService`.
The internal biology model may be richer, but the adapter must translate to and
from these shared types:

- `ConstructRef`
- `ConstructSummary`
- `ValidationResult`

The adapter will be loadable through the existing bootstrap seam:

```text
DNA_MAKER_BIOLOGY_ADAPTER=dnamaker.service:create_biology_adapter
```

The adapter will not import, launch, or require SnapGene. `snapgene` artifacts
remain Person 1's responsibility.

## Artifact and path semantics

- `ConstructRef.path` is relative to the configured MCP workspace, as defined
  by the shared contract. The adapter must not interpret it relative to an
  individual developer's home directory.
- Person 2 accepts `genbank`, `fasta`, and `json` inputs. A `snapgene` input is
  rejected with an explicit biology error; it must first be converted by
  Person 1.
- `read_construct` preserves the input artifact and returns a summary of it.
- `replace_region` and `add_annotation` write a new intermediate artifact and
  return its `ConstructRef`; they never overwrite the input artifact.
- Intermediate mutation artifacts are written below the configured workspace
  artifact directory. Callers must use the returned path and must not infer a
  filename.
- For the hackathon, a shared local workspace and collision-resistant paths are
  sufficient; content-addressed storage and cross-machine artifact transfer
  are deferred until the VPS/Windows workflow is exercised.
- `save_construct` writes to the caller-supplied `output_path`. Supported
  output formats are `genbank`, `fasta`, and `json`; `snapgene` output belongs
  to Person 1.

## Internal domain conventions

The engine uses a domain model equivalent to:

```text
Construct:
  name: string
  sequence: uppercase DNA string
  topology: circular | linear
  features: list[Feature]
  primers: list[Primer]
  metadata: JSON object

Feature:
  name: string
  type: string
  start: integer
  end: integer
  strand: 1 | -1
  qualifiers: JSON object
```

- Coordinates are always 0-based and end-exclusive: `[start, end)`.
- `start < end` for a single interval.
- Lowercase DNA is normalized to uppercase; non-IUPAC DNA symbols are
  rejected.
- GenBank's 1-based inclusive locations are converted only at the I/O
  boundary.
- GenBank `/label` is the preferred source for `Feature.name`; `/gene` and
  `/note` are preserved as qualifiers rather than silently discarded.
- Validation checks bounds and strand values. General feature overlap is
  allowed because biologically meaningful annotations can overlap.

## Adapter method semantics

### `read_construct(construct: ConstructRef) -> ConstructSummary`

Loads the referenced artifact and returns:

```json
{
  "construct": {"path": "inputs/example.gb", "format": "genbank", "name": "pExample"},
  "sequence_length": 1000,
  "topology": "circular",
  "features": [
    {
      "name": "GFP",
      "type": "CDS",
      "start": 100,
      "end": 850,
      "strand": 1,
      "qualifiers": {}
    }
  ]
}
```

For FASTA without topology metadata, the adapter treats the construct as
linear. GenBank topology is preserved when declared and otherwise defaults to
linear.

### `replace_region(...) -> ConstructRef`

- `target` resolves to exactly one `Feature.name`; matching is exact and
  case-sensitive. No substring or fuzzy matching is performed.
- Zero matches and multiple matches are errors requiring caller input.
- The target feature's `[start, end)` interval is replaced with
  `replacement_sequence`.
- Features wholly downstream shift by the sequence-length delta.
- A partially overlapping unrelated feature is rejected rather than silently
  moved or truncated.
- If `replacement_name` is provided, the replacement is annotated with that
  name and the target feature's type; if it is `None`, no replacement feature
  is created.
- Origin-spanning circular feature edits are rejected in the MVP until a
  multi-part location representation is implemented.

### `add_annotation(...) -> ConstructRef`

- Requires `0 <= start < end <= sequence_length`.
- Requires `strand` to be `1` or `-1`.
- Creates a feature with the supplied name and type.
- Overlap with existing features is permitted.
- The operation is a mutation and therefore invalidates any previous
  validation result through the shared workflow manager.

### `find_restriction_sites(...) -> list[dict]`

Each site dictionary has this stable minimum shape:

```json
{
  "position": 123,
  "strand": 1,
  "site": "GGTCTC"
}
```

`position` is the 0-based start of the recognition site in the stored forward
sequence. Results are sorted by position and then strand. Circular origin-
spanning sites are normalized to their start position when the enzyme's
recognition sequence crosses the origin.

### `validate_construct(...) -> ValidationResult`

Every check contains at least `name` and `passed`; optional `details` must be
JSON serializable. The initial stable check names are:

```text
sequence_alphabet
topology
feature_bounds
feature_strands
```

`valid` is true only when every required check passes. The adapter returns a
false result for biological invalidity and raises only when validation itself
cannot be performed.

## Deferred hardening and one shared follow-up

The following do not block Person 2's first adapter:

- Typed result models can replace the current `dict` payloads after the first
  end-to-end workflow.
- Content hashes, durable workflow state, and cross-machine artifact transfer
  can be added when the VPS/Windows execution path is introduced.
- Circular origin-spanning edits remain out of scope for the first demo.
- Dedicated `BiologyError` code mapping can be added after the adapter works;
  the adapter raises exceptions and never returns MCP `{ok: false}` payloads.

One item is outside Person 2's plan and should be a small shared follow-up:

- `WorkflowManager.snapgene_open` currently accepts an arbitrary path without
  calling `_require_validated_construct`, despite the shared contract requiring
  validation before opening the current construct. Person 3 should add the
  gate or explicitly document the temporary exception.

Until the hardening work is scheduled, the defaults above are the Person 2
implementation assumptions.
