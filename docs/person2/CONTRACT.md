# Person 2 biology-engine contract

This file supplements the shared [component contract](../../CONTRACT.md). The
shared contract remains authoritative at the integration boundary. This file
defines the biology-specific behavior that the shared contract intentionally
leaves open.

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

## Open terms for team confirmation

These are the only remaining decisions that may need negotiation with Persons
1 and 3:

1. Confirm the artifact-directory configuration and collision-resistant naming
   policy for mutation results.
2. Confirm whether the shared contract should add typed models for restriction
   sites and validation checks instead of `dict` payloads.
3. Confirm whether circular, origin-spanning features are required for the
   first integrated demo or can remain outside the MVP.
4. Confirm the shared error-code mapping for `BiologyError`; the adapter will
   raise exceptions and will never return MCP `{ok: false}` payloads itself.

Until those terms are changed in the shared contract, the defaults above are
the Person 2 implementation assumptions.
