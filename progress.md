Started Gibson MVP for a ten-minute presentation deadline. Working tree was clean.
Implemented assembly engine, adapter/workflow/MCP operation, and optional SnapGene startup.
Full test suite: 49 passed, 2 skipped (live SnapGene), one dependency forward-reference warning.
Demo passed seven independent verification checks, output in artifacts/gibson-demo-20260912-192118-eb75ef/.
Added README/contract/agent instructions and docs/GIBSON_DEMO.md presentation notes.
PR CI follow-up: reproduced two pre-existing repository-wide lint failures in tests/test_biology_adapter.py (I001) and tests/test_mcp_stdio.py (SIM117). Sorted imports and combined async context managers without changing behavior. Full CI lint command passes; pytest remains 49 passed, 2 skipped, one dependency warning. Earlier changed-files lint scope missed these baseline errors.
Merged origin/main at 88aa90a using the repository's merge-commit convention. Resolved README conflict by retaining main's corrected SnapGene prompts and this branch's Gibson guide. Preserved new manuals and real MCP SnapGene runner. Verification: locked dependency sync, full CI lint, 49 passing tests (2 live tests skipped, existing dependency warning), successful wheel/sdist build, passing Gibson demo, and new runner --help smoke check.
