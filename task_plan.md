# Task Plan: Person 2 Molecular Biology Engine — Today’s MVP

## Goal

By the end of today, deliver an installable, SnapGene-independent Python package that represents constructs, reads/writes GenBank and FASTA, performs safe core sequence/feature operations, scans restriction sites, simulates exact-match PCR, validates constructs, and proves the behavior with tests and a clear handoff contract.

## Current Phase

Phase 1 — Requirements & Discovery

## Phases

### Phase 1: Requirements & Discovery

- [x] Confirm that “person 2” means the molecular biology engine in `SCOPE.md`
- [x] Inspect the repository and existing toolchain
- [x] Define a finishable MVP for one day
- [x] Document findings in `findings.md`
- **Status:** complete

### Phase 2: Planning & Structure

- [x] Choose the Python package layout
- [x] Define the canonical construct/feature data contract
- [x] Define coordinate, topology, alphabet, and error-handling rules
- [x] Define explicit non-goals for today
- **Status:** complete

### Phase 3: Implementation

- [ ] Bootstrap the package with `uv`
- [ ] Implement `Construct`, `Feature`, and `Location` models
- [ ] Implement GenBank and FASTA I/O
- [ ] Implement reverse complement, translation, replace-region, and feature operations
- [ ] Implement restriction-site scanning
- [ ] Implement exact-match PCR simulation
- [ ] Implement construct validation and useful exceptions
- [ ] Add a small CLI or documented Python API for a smoke test
- **Status:** pending

### Phase 4: Testing & Verification

- [ ] Add deterministic fixtures and unit tests for each module
- [ ] Add round-trip GenBank and FASTA tests
- [ ] Add edge-case tests: invalid DNA, out-of-bounds features, circular topology, reverse strand, and no PCR product
- [ ] Run `uv run pytest`, lint/format checks, and a fresh-environment install check
- [ ] Record actual results in `progress.md`
- **Status:** pending

### Phase 5: Integration Handoff

- [ ] Document the public API and JSON/GenBank interchange assumptions
- [ ] Give Person 1 a sample GenBank output and coordinate convention
- [ ] Give Person 3 stable function names, schemas, and validation/error behavior
- [ ] Commit the MVP as one reviewable change set
- **Status:** pending

## Key Questions

1. What is the canonical interchange representation between Person 2, Person 1, and Person 3? — Use structured JSON/Pydantic internally and GenBank as the biological artifact format.
2. What coordinate convention prevents integration bugs? — Use 0-based, half-open intervals internally; convert only at GenBank boundaries.
3. What can be safely finished today? — Core representation, I/O, deterministic sequence operations, restriction scanning, exact-match PCR, validation, tests, and handoff docs.
4. What should not block today’s MVP? — `.dna` parsing, GUI/SnapGene behavior, thermodynamic primer design, optimized assembly design, and full biological rule coverage.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Python package under `src/dnamaker_bio/` | Matches the project scope and keeps the biology layer independent of SnapGene and the agent layer. |
| Use `uv` for environment and dependency management | `uv` is installed in the repository environment and gives reproducible commands with a lockfile. |
| Use Biopython for GenBank/FASTA and restriction primitives | Avoids reimplementing established file parsing and enzyme definitions. Keep project-specific behavior in our own modules. |
| Use Pydantic models for `Construct`, `Feature`, and `Location` | Gives Person 3 a serializable, validated contract and makes invalid operations explicit. |
| Internal coordinates are 0-based, half-open | Python-friendly and unambiguous; GenBank’s 1-based inclusive locations are an I/O concern. |
| Reject ambiguous feature-overlap edits in the MVP | Silent annotation corruption is worse than a clear error. Add explicit edit policies later. |
| Exact-match PCR simulation only today | It is deterministic and testable; primer thermodynamics/design is a separate milestone. |
| `.dna` is out of scope for the engine | Person 1 owns SnapGene conversion; the engine’s handoff is GenBank plus structured JSON. |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| None | 1 | No implementation work has started yet. |

## Notes

- The repository currently contains only `README.md` and `SCOPE.md`; there is no existing Python package to preserve.
- The plan is intentionally a vertical slice. Do not spend the day implementing every item in the broad scope list.
- A feature is not “done” until it has a test and its public behavior is documented.
- Update this file and `progress.md` after each phase; record all test failures before retrying.
