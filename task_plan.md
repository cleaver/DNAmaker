# Gibson MVP
1. Implement ordered exact-overlap assembly and annotation mapping — complete.
2. Expose adapter/workflow/MCP and allow biology-only startup — complete.
3. Test junctions, circular features, validation gates; run presentation demo — complete.
Scope: pre-oriented linear fragments, explicit overlap lengths, no primer design.

## Errors encountered
- AppImage launcher redirected Python executable discovery; run with APPIMAGE unset or via uv.
- Lint found unused test imports/import ordering; fixed with ruff.
4. Diagnose and fix PR CI lint failures — complete; remote CI passed.
- Full-repository lint exposed two existing test style violations; fixed and rechecked with the exact CI command.

5. Merge latest main, preserve both documentation changes, build and verify — complete.
6. Audit and fix remaining uppercase boundaries and verification comparisons — complete; regression tests pass.
