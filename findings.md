# Findings & Decisions

## Requirements

- Person 2 owns the molecular biology engine, independent of SnapGene.
- The engine needs sequence manipulation, feature/annotation manipulation, primer handling, restriction analysis, ORF/translation, PCR simulation, assembly logic, validation, and biological rules over time.
- The shared interchange should be GenBank plus a structured JSON representation.
- Person 1 owns SnapGene integration; Person 3 owns agent/MCP/orchestration.
- Today’s achievable MVP must establish the core contract and a working, tested vertical slice rather than implement the entire long-term scope.

## Research Findings

- `SCOPE.md` is the only project-specific design document besides `README.md`.
- The repository is otherwise empty and clean on branch `main` tracking `origin/main`.
- Python `3.14.7` and `uv 0.9.22` are available; Poetry is not installed.
- The scope itself proposes Python, Biopython, Pydantic, and primer3. For today, primer3 is deferred until the core contract and tests exist.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| `Construct` is the central domain object | All sequence and annotation operations can be composed without a SnapGene process. |
| `Construct` fields: `name`, `sequence`, `topology`, `features`, `primers`, `metadata` | Mirrors the project’s proposed JSON and leaves room for future primer/metadata support. |
| `Feature` has name/type/location/strand/qualifiers | Enough for GenBank round-tripping and agent-facing annotation operations. |
| `Location` uses 0-based half-open `[start, end)` intervals and optional parts | Avoids off-by-one errors and leaves a path for origin-spanning circular features. |
| Accept IUPAC DNA symbols, normalize lowercase to uppercase, reject other symbols | Supports real sequence data without silently accepting corrupted input. |
| GenBank is the primary artifact; FASTA is sequence-only | Preserves annotations while still supporting common input/output. |
| Refuse a sequence edit that partially overlaps an existing feature unless an explicit policy is added | Prevents the most dangerous MVP failure: annotations silently describing the wrong bases. |
| PCR requires exact primer binding matches and returns a structured product | Deterministic baseline for later primer design and mismatch/thermodynamic logic. |

## Proposed Package Layout

```text
pyproject.toml
uv.lock
src/dnamaker_bio/
  __init__.py
  models.py
  io.py
  sequence.py
  features.py
  restriction.py
  pcr.py
  validation.py
  errors.py
  cli.py                 # optional thin smoke-test entry point
tests/
  fixtures/
    mini_construct.gb
    mini_sequence.fasta
  test_models.py
  test_io.py
  test_sequence.py
  test_features.py
  test_restriction.py
  test_pcr.py
  test_validation.py
README.md
```

## Today’s Acceptance Criteria

- A clean checkout can install the package and run the test suite with `uv sync && uv run pytest`.
- A GenBank fixture loads into `Construct`, saves, and loads back without sequence or feature loss.
- FASTA loads/saves sequence and name correctly; annotations are not invented.
- Reverse complement and translation have known-answer tests.
- `replace_region` shifts downstream features and rejects unsafe partial feature overlap.
- Restriction scanning returns enzyme, site, and positions using the documented coordinate convention.
- Exact-match PCR returns one expected amplicon and a clear no-product result/error.
- Validation catches bad DNA, invalid topology, out-of-bounds features, and malformed strands.
- Person 1 can consume a documented GenBank artifact; Person 3 can call stable Python functions or serialize the Pydantic model.

## Explicitly Deferred

- SnapGene `.dna` parsing/conversion and GUI automation.
- Primer3 integration, primer scoring, Tm/GC optimization, and primer design UI.
- Gibson/Golden Gate/restriction cloning design beyond reusable restriction-site scanning.
- ORF search beyond a basic translation helper.
- Full biological validation rules, codon optimization, and wet-lab protocol recommendations.

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| No existing package scaffold or dependency file | Plan to bootstrap with `uv` in Phase 3. |

## Resources

- Project scope: `SCOPE.md`
- Project overview: `README.md`
- Planned package root: `src/dnamaker_bio/`

## Visual/Browser Findings

- None; this task required repository inspection only.
