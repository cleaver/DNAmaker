# Gibson assembly presentation

Run from the project root:

```sh
uv run python -m dnamaker.gibson_demo
```

If the application launcher affects Python, use:

```sh
env -u APPIMAGE .venv/bin/python -m dnamaker.gibson_demo
```

## What to say

“DNAmaker now simulates Gibson assembly locally without SnapGene. We provide two
linear DNA fragments with matching end overlaps. The engine checks both junctions,
collapses the shared sequence, preserves annotations, and saves a circular GenBank
product. The workflow requires validation before saving and records the operations.”

“The demonstration combines a 110-base synthetic vector fragment and a 90-base
synthetic insert. The two shared 20-base overlaps occur once in the final product,
so the result is 160 bases. The verification checks the expected sequence, length,
circular topology, preserved annotations, both junctions, unchanged source files,
and the validation gate.”

## What is included

- Real Python assembly engine, file-backed adapter, workflow operation, and MCP tool.
- Circular and linear products from two or more ordered fragments.
- Explicit exact overlap lengths; invalid joins fail with structured errors.
- GenBank output, junction annotations, provenance, and workflow log.
- Linux biology-only startup; Windows and SnapGene are unnecessary.

## Scope of this demonstration

Sequences are synthetic teaching fixtures, not a functional plasmid. Input fragments
must already be linear, oriented, and contain their overlaps. Primer design,
automatic fragment preparation/order/orientation, mismatch handling, alternative
assembly detection, experimental efficiency prediction, and SnapGene GUI/history
are outside this MVP. Structural validation does not establish experimental success.

## Artifacts

Every run creates a unique `artifacts/gibson-demo-*/` folder. Open `assembled.gb`
for the sequence and features, `verification.json` for pass/fail evidence, and
`workflow.json` for the operation history.
