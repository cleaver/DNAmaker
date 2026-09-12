**TL;DR:** I’d split it into **3 largely independent layers**:

1. **SnapGene integration + GUI automation**
2. **Molecular biology/sequence engine**
3. **Agent/MCP layer + orchestration**

The key is to define a **clean contract between them** so nobody has to wait for another person.

### Person 1 — SnapGene integration

**Owns everything that talks to SnapGene.**

Build:

* SnapGene CLI wrapper
* `.dna` ↔ GenBank/FASTA conversion
* DNA map rendering
* Opening files in SnapGene
* GUI automation for functionality unavailable through CLI
* Detecting SnapGene windows/dialogs
* Clicking/typing/selecting in SnapGene
* Automating:

  * cloning workflows
  * PCR
  * Gibson
  * Golden Gate
  * restriction cloning
  * primer workflows
  * sequence editing
  * annotations
* Robustness/retry/error handling

**Deliverable:** a Python/TypeScript library where the other two people don't need to know anything about GUI automation.

For example:

```python
snapgene.open("plasmid.dna")

snapgene.insert_sequence(
    file="plasmid.dna",
    position=1234,
    sequence="ATGC..."
)

snapgene.run_gibson(
    fragments=["a.dna", "b.dna"]
)

snapgene.export(
    "result.dna",
    format="genbank"
)
```

Even if internally this involves UI automation, **the interface stays clean**.

---

### Person 2 — Molecular biology engine

**Owns the actual sequence intelligence.**

This should ideally work **without SnapGene running**.

Build:

* GenBank parser/writer
* FASTA handling
* `.dna` handling where practical
* Sequence manipulation
* Feature/annotation manipulation
* Primer handling
* Restriction-site analysis
* ORF detection
* Translation
* Reverse complement
* PCR simulation
* Primer design
* Gibson assembly logic
* Golden Gate logic
* Restriction cloning logic
* Sequence validation
* Construct validation
* Biological constraints/rules

Potential stack:

```text
Python
├── Biopython
├── pydantic
├── primer3
└── your own molecular-biology logic
```

The important architectural principle:

> **The biology engine should not depend on SnapGene.**

For example:

```python
construct = load_genbank("plasmid.gb")

construct = replace_region(
    construct,
    old="GFP",
    new="mCherry"
)

construct = add_feature(
    construct,
    ...
)

validate_construct(construct)

save_genbank(construct, "result.gb")
```

Then Person 1 can take `result.gb` and turn it into a SnapGene file.

---

### Person 3 — Agent / MCP / orchestration

**Owns the AI-facing interface.**

Build the actual agent that turns natural language into operations.

For example:

> "Take pUC19, replace GFP with mCherry, add a CMV promoter, verify that there are no internal BsaI sites, and open the result in SnapGene."

Agent decides:

```text
1. Load pUC19
2. Find GFP
3. Replace GFP → mCherry
4. Add CMV annotation
5. Scan BsaI sites
6. Validate construct
7. Save GenBank
8. Convert to .dna
9. Open in SnapGene
```

Expose tools like:

```text
read_construct()
modify_sequence()
add_annotation()
remove_annotation()
find_sites()
design_primers()
simulate_pcr()
assemble_gibson()
validate_construct()
save_construct()

snapgene_open()
snapgene_export()
snapgene_render()
snapgene_run_workflow()
```

Person 3 owns:

* MCP/tool definitions
* Agent prompts
* Planning
* Tool selection
* State management
* Conversation → structured operations
* Validation before destructive operations
* Error recovery
* Tests of complete workflows
* User-facing interface

---

# The architecture I'd use

```text
                    ┌────────────────────┐
                    │       AGENT        │
                    │                    │
                    │ Natural language   │
                    │ planning           │
                    │ tool selection     │
                    └─────────┬──────────┘
                              │
                         MCP / tools
                              │
               ┌──────────────┴──────────────┐
               │                             │
               ▼                             ▼
     ┌──────────────────┐          ┌──────────────────┐
     │ MOLECULAR ENGINE  │          │ SNAPGENE BRIDGE  │
     │                  │          │                  │
     │ Biopython        │          │ CLI              │
     │ Sequence editing │          │ GUI automation   │
     │ Primers          │          │ .dna             │
     │ Assembly         │          │ Rendering        │
     │ Validation       │          │ SnapGene actions │
     └────────┬─────────┘          └────────┬─────────┘
              │                             │
              └──────────────┬──────────────┘
                             ▼
                     ┌──────────────┐
                     │ GenBank / DNA │
                     │   artifacts   │
                     └──────────────┘
```

## Most important: define the interface on Day 1

Don't let Person 1 and Person 2 build around each other's implementation.

Agree on a **canonical construct representation**.

I'd make **GenBank + a structured JSON representation** the central interchange format.

Something like:

```json
{
  "name": "pExample",
  "sequence": "ATGC...",
  "topology": "circular",
  "features": [
    {
      "name": "CMV",
      "type": "promoter",
      "start": 100,
      "end": 650,
      "strand": 1
    }
  ],
  "primers": [],
  "metadata": {}
}
```

Then everyone's work becomes independent:

```text
Person 2
JSON/GenBank
      ↓
  biology

Person 1
JSON/GenBank
      ↓
  SnapGene

Person 3
natural language
      ↓
JSON/tool calls
```

### Git repository structure

I'd also split the repo physically:

```text
snapgene-agent/
│
├── agent/
│   ├── planner/
│   ├── tools/
│   └── prompts/
│
├── biology/
│   ├── sequence/
│   ├── primers/
│   ├── assembly/
│   ├── restriction/
│   └── validation/
│
├── snapgene/
│   ├── cli/
│   ├── gui/
│   └── workflows/
│
├── schemas/
│   ├── construct.json
│   ├── feature.json
│   └── operation.json
│
└── tests/
    ├── biology/
    ├── snapgene/
    └── integration/
```

This gives you **three teams that can genuinely work simultaneously** rather than three people constantly blocking each other.

### One additional thing I'd assign

Have **Person 3 build the integration-test suite from the beginning**, even while the others are developing.

Create tests such as:

```text
User request
    ↓
Agent
    ↓
tool calls
    ↓
expected construct
    ↓
SnapGene
    ↓
expected .dna / screenshot / GenBank
```

Then by the end you can test the whole system rather than discovering that the three components don't actually work together.

**My preferred ownership:**

| Person | Primary responsibility          | Dependency      |
| ------ | ------------------------------- | --------------- |
| **1**  | SnapGene + GUI automation       | Schema          |
| **2**  | Biology/sequence engine         | Schema          |
| **3**  | Agent + MCP + integration tests | Both interfaces |

The **schema/API contract should be the first thing all 3 agree on**. Once that's frozen, they can work almost completely in parallel.
