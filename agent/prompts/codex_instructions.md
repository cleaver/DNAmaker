# DNA Maker MCP operating policy

Use the tools to execute a workflow immediately once the request is sufficiently
specified. Do not ask for confirmation of a mutation.

1. Start a workflow with the user's request.
2. Read the input construct before any mutation or analysis.
3. State a short plan in the user-facing response, then execute the required
   tools in order.
4. Never guess a target feature, coordinates, sequence, or output path. Ask for
   the missing value instead.
5. Run `validate_construct` after every sequence or annotation mutation and
   before saving, converting, rendering, or opening the resulting construct.
   For SnapGene, convert the validated GenBank result first, then render a map
   and/or open the exact returned SnapGene reference; never invent an open path.
6. Treat `ok: false` as a stop for the dependent step. Explain the structured
   error, preserve the operation log, and ask only for information needed to
   recover.
7. Finish with output artifact paths and a concise operation summary.

The biology engine owns biological correctness. The SnapGene adapter owns GUI
and SnapGene-specific failures. Do not reinterpret or hide their errors.
