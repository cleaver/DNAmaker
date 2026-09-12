# Task Plan: Person 2 Molecular Biology Engine — Today’s MVP

## Goal

Next milestone: deliver a working `agent.adapters.BiologyService` implementation so Person 3 can run a real biology workflow and Person 1 can consume its GenBank output. Build only the supporting biology logic needed for its six methods. Broader engine features follow this integration milestone.

## Current Phase

Phase 5 — Integration handoff complete

## Delivered Milestone: BiologyService Adapter

Implement `dnamaker.service:create_biology_adapter`, a zero-argument factory returning an adapter with the exact signatures in `agent/adapters.py` and shared return types from `agent/models.py`.

1. Establish the factory and workspace handling in the existing `src/dnamaker/` package. Default the workspace to the process working directory; allow explicit workspace injection when constructing the adapter for tests. Write unique mutation artifacts under `artifacts/biology/` and preserve inputs.
2. Implement `read_construct`, `validate_construct`, and `save_construct` with real GenBank I/O first. Return `ConstructSummary` and `ValidationResult` objects, not lookalike dictionaries. Add FASTA/JSON handling as promised by the Person 2 supplement before declaring the milestone complete; JSON round trips must use one documented schema.
3. Implement `add_annotation` and `replace_region` using the supplement's coordinate, target-matching, and overlap rules. Each mutation returns a new on-disk GenBank artifact. Resolve replacement orientation and contained/containing annotation behavior explicitly in tests before implementing edits; reject unsupported cases rather than losing annotations silently.
4. Implement `find_restriction_sites` with the supplement's recognition-site coordinates and deterministic result ordering, including circular origin-crossing recognition sites.
5. Exercise the real adapter through `WorkflowManager`: read → replace → annotate → scan → validate → save. Use a fake SnapGene adapter only for the final conversion/open handoff, so the test runs without Windows or SnapGene.
6. Provide a small input fixture, generated GenBank output, and factory configuration instructions for the group.

### Acceptance Criteria for Review

- All six protocol methods perform real supported operations; no placeholder success results.
- The factory loads through the existing `module:factory` bootstrap mechanism.
- GenBank sequence, topology, and supported annotations survive a read/save/read round trip; FASTA's annotation loss is explicitly documented.
- Mutation output exists, has a new path, and leaves the input bytes unchanged.
- Missing/ambiguous targets, invalid coordinates, unsupported formats and unsafe edits fail clearly.
- Required validation checks return stable `name`/`passed` fields, with a false result for inspectable invalid constructs. Read/parse failures raise exceptions.
- Known-answer tests cover edits, downstream feature shifts, restriction coordinates and validation failures. The real-adapter workflow test verifies export remains gated after a mutation.
- Existing workflow tests continue to pass; no SnapGene installation is needed for biology tests.

### Deferred Until After Adapter Handoff

PCR simulation, primer design, translation/ORF tools, assembly workflows, a new CLI, and a comprehensive internal model framework are subsequent work. Add internal helpers/models only as needed by the six adapter methods.

## Hackathon Mode

- Treat `docs/person2/CONTRACT.md` as the working agreement for this segment.
- Do not block implementation on typed payloads, content-addressed artifacts,
  durable workflow state, or origin-spanning circular edits.
- Ask Person 3 to make the one shared follow-up: enforce the validation gate in
  `WorkflowManager.snapgene_open`.

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
- [x] Align the adapter boundary with the shared `CONTRACT.md`
- [x] Define coordinate, topology, alphabet, and error-handling rules
- [x] Define explicit non-goals for today
- **Status:** complete

### Phase 3: BiologyService Adapter Implementation

- [x] Bootstrap the package with `uv` (existing scaffold)
- [x] Implement `dnamaker.service:create_biology_adapter` for the shared bootstrap seam
- [x] Implement only the internal representation/helpers needed by the adapter
- [x] Implement GenBank, FASTA and documented JSON I/O
- [x] Implement replace-region and annotation operations
- [x] Implement restriction-site scanning
- [x] Implement construct validation and useful exceptions
- [x] Document the factory and real workflow smoke test
- **Status:** complete

### Phase 4: Testing & Verification

- [x] Add deterministic fixtures and unit tests for each module
- [x] Add round-trip GenBank and FASTA tests
- [x] Add edge-case tests: invalid DNA, out-of-bounds features, circular topology, reverse strand, and ambiguous targets
- [x] Test the real BiologyService adapter through WorkflowManager with fake SnapGene only
- [x] Run `uv run pytest`, scoped lint/format checks, and a fresh-environment install check
- [x] Record actual results in `progress.md`
- **Status:** complete

### Phase 5: Integration Handoff

- [x] Document the public API and JSON/GenBank interchange assumptions
- [x] Document the Person 2 supplement and any terms requiring team confirmation
- [x] Give Person 1 a sample GenBank fixture and coordinate convention
- [x] Give Person 3 stable function names, schemas, and validation/error behavior
- [x] Commit the MVP as one reviewable change set
- **Status:** complete

## Key Questions

1. What is the canonical interchange representation between Person 2, Person 1, and Person 3? — Use structured JSON/Pydantic internally and GenBank as the biological artifact format.
2. What coordinate convention prevents integration bugs? — Use 0-based, half-open intervals internally; convert only at GenBank boundaries.
3. What is the next delivery? — All six BiologyService methods, factory loading, supporting I/O and biology operations, real-adapter workflow tests, and a GenBank handoff artifact.
4. What should not block today’s MVP? — `.dna` parsing, GUI/SnapGene behavior, thermodynamic primer design, optimized assembly design, typed result models, durable artifact storage, origin-spanning edits, and full biological rule coverage.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Python package under `src/dnamaker/` | Matches the existing scaffold while keeping the biology layer independent of SnapGene. |
| Implement the shared `agent.adapters.BiologyService` at a thin adapter boundary | Keeps Person 3's orchestration stable while allowing richer Person 2 domain models internally. |
| Expose `dnamaker.service:create_biology_adapter` | Matches `agent.bootstrap`'s existing `module:factory` loading seam. |
| Use `uv` for environment and dependency management | `uv` is installed in the repository environment and gives reproducible commands with a lockfile. |
| Use Biopython for GenBank/FASTA and restriction primitives | Avoids reimplementing established file parsing and enzyme definitions. Keep project-specific behavior in our own modules. |
| Defer a comprehensive internal model framework | Person 3 consumes the existing shared dataclasses; internal models are implementation choices and must not delay the adapter. |
| Internal coordinates are 0-based, half-open | Python-friendly and unambiguous; GenBank’s 1-based inclusive locations are an I/O concern. |
| Reject ambiguous feature-overlap edits in the MVP | Silent annotation corruption is worse than a clear error. Add explicit edit policies later. |
| Defer PCR until after adapter handoff | PCR is not one of the six shared protocol methods. |
| `.dna` is out of scope for the engine | Person 1 owns SnapGene conversion; the engine’s handoff is GenBank plus structured JSON. |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| Whole-construct `source` feature blocked replacement | 1 | Allow the canonical source feature to resize with the construct; continue rejecting other overlapping features. |
| Circular BsaI test expected position 4 for a site beginning at 3 | 1 | Correct the known-answer expectation to the documented 0-based start. |
| Build command rejected because it included recursive deletion of a temp directory | 1 | Use a fresh `mktemp` output directory and avoid deletion. |
| Direct invocation of the symlinked fresh-venv Python omitted the venv from `sys.path` | 1 | Re-run with `VIRTUAL_ENV` explicitly set; the wheel contents and install records are correct. |

## Notes

- The repository now includes the upstream agent/MCP foundation and a `src/dnamaker/` scaffold; the biology implementation should integrate behind the existing adapter protocol.
- The shared contract is at the repository root; Person 2-specific details live in `docs/person2/CONTRACT.md`.
- Personal planning files live under `docs/person2/` so they do not appear to be shared project policy.
- In hackathon mode, the Person 2 supplement is sufficient to proceed; only the `snapgene_open` validation-gate mismatch needs a shared implementation follow-up.
- The plan is intentionally a vertical slice. Do not spend the day implementing every item in the broad scope list.
- A feature is not “done” until it has a test and its public behavior is documented.
- Scoped Ruff checks pass for Person 2 files. Repository-wide Ruff still reports a pre-existing `BLE001` in `agent/server.py` and formatting drift in upstream files; those unrelated files were left untouched.
- Update this file and `progress.md` after each phase; record all test failures before retrying.
