# Nolane Habitat — Agent-Native Workspace
## Research, architecture, and implementation plan

**Status:** pre-implementation research blueprint  
**Working name:** Nolane Habitat  
**Core idea:** compile ordinary project files into a persistent, versioned, AI-native semantic workspace while keeping the external source tree synchronized and human-usable.  
**Scope boundary:** folders, ZIP archives, and ordinary project files only. No attempt to replace Windows, Linux, macOS, or the desktop operating environment.

---

# 0. Executive thesis

The project should not build a prettier file manager for AI and should not merely add semantic search to a repository. The target is a new **agent-computer interface for project work**.

Traditional software projects expose information through primitives optimized for humans and generic programs:

- directories and paths;
- text files;
- terminal commands and stdout;
- editor buffers;
- browser pixels;
- build logs;
- test logs.

An AI agent therefore wastes work on orientation and reconstruction:

`list -> search -> open -> read -> cross-reference -> remember -> execute shell -> parse logs -> open UI -> inspect again`.

Nolane Habitat changes the primitive interface. A project is ingested once and compiled into a **Semantic Twin**. The agent enters that twin and receives typed, queryable objects representing the project and its current execution state.

The external project remains ordinary source code. Humans can still open the folder, run the app, inspect files, use Git, or package it as a ZIP. Habitat is a semantic and transactional control plane over that source, not a proprietary replacement for source code.

The fundamental invariant is:

> **Source files remain the executable truth; Habitat provides an incrementally compiled cognitive representation of that truth.**

The long-term experience should be closer to this:

```text
User task
   |
   v
workspace.orient(task)
   |
   +--> project architecture slice
   +--> relevant symbols and contracts
   +--> dependencies and callers
   +--> targeted tests/build actions
   +--> current diagnostics
   +--> UI surfaces, if applicable
   +--> unresolved/low-confidence regions
   |
   v
agent reasons and changes semantic objects
   |
   v
transaction -> source synchronization -> incremental recompilation
   |
   v
structured verification receipts
```

rather than this:

```text
ls
find
grep
cat
sed
open files
npm test
read 6,000 lines of logs
open browser
look at screenshots
repeat
```

---

# 1. Scope contract

## 1.1 In scope

Habitat accepts:

1. a normal source folder;
2. a ZIP archive containing a project;
3. one or more normal files;
4. mixed-language projects;
5. web projects whose UI can be rendered in a browser runtime.

Initial language targets:

- Python;
- JavaScript;
- TypeScript;
- Java;
- HTML;
- CSS;
- JSON;
- YAML;
- Markdown;
- XML;
- common project manifests and build files.

The architecture must permit later language plugins without changing the agent protocol.

## 1.2 Explicitly out of scope for the first product

- operating-system replacement;
- desktop automation across arbitrary applications;
- Windows UI automation;
- macOS UI automation;
- Linux desktop automation;
- arbitrary remote-computer control;
- mobile UI automation;
- full binary reverse engineering;
- model training;
- autonomous deployment to production;
- treating generated semantic summaries as canonical source truth.

## 1.3 Important distinction

Habitat may internally use processes, language servers, a headless browser, containers, or operating-system APIs. That is implementation machinery. The **agent-facing abstraction must not leak those human/computer-centric interfaces unless a fallback is necessary**.

---

# 2. Product doctrine

## Doctrine A — Files are backing storage, not the main cognitive primitive

The agent should normally operate on:

- project objects;
- modules;
- symbols;
- relations;
- tests;
- diagnostics;
- build tasks;
- runtime services;
- UI elements;
- transactions;
- evidence receipts.

Exact file bytes remain available on demand for precision and editing, but whole-file reading is no longer the default navigation strategy.

## Doctrine B — Front-load understanding, amortize it across every task

Cold ingestion may do substantial deterministic work once:

- identify project types;
- hash source;
- parse syntax;
- discover symbols;
- resolve imports/references;
- build graphs;
- index text;
- discover build/test tasks;
- derive project/module summaries;
- detect UI entrypoints.

After that, edits trigger incremental invalidation and recompilation only for affected regions.

## Doctrine C — Context is compiled per task

The repository is not dumped into the LLM context. A Context Compiler creates a small task-specific slice based on:

- intent;
- graph proximity;
- symbol relevance;
- changed code;
- tests;
- diagnostics;
- manifests;
- documentation;
- UI/runtime state;
- confidence and freshness.

## Doctrine D — Every generated interpretation is provenance-bound

A module summary, architecture description, or inferred invariant must carry:

- source object references;
- source revision/digest;
- method of derivation;
- confidence;
- invalidation dependencies.

No summary becomes equivalent to source truth.

## Doctrine E — Execution is an action, not a terminal session

The agent requests structured actions. Examples:

```text
build.run(target="app")
test.run(scope="memory")
lint.run(changed=true)
server.start(target="web")
http.request(service="web", path="/")
process.stop(run_id="...")
```

The implementation may start subprocesses, but the agent receives a typed receipt rather than a terminal screen.

## Doctrine F — UI is a semantic surface first, pixels second

For web UI, the primary observation should combine:

- accessibility tree;
- DOM semantics;
- element roles/names/states;
- layout rectangles;
- visibility;
- computed style subset;
- event/action targets;
- console errors;
- network failures;
- route and application state where observable.

Screenshots remain a secondary sensor for appearance problems that cannot be represented structurally.

## Doctrine G — Source synchronization is transactional

Agent edits are committed through versioned transactions. Every transaction checks the source revision it was based on. External changes are watched and incrementally recompiled. Conflicts are explicit; no silent overwrites.

---

# 3. What current systems solve — and what remains unsolved

Habitat should reuse proven mechanisms without copying their product boundaries.

## 3.1 Aider repository map

Aider demonstrates that a compact repository map built from symbols and dependency ranking can materially reduce the amount of code that must be placed in context. Its repo map uses Tree-sitter and graph ranking to select important definitions under a token budget.

**Lesson for Habitat:** project orientation must be precompiled and ranked, not rediscovered with repeated grep/read loops.

**What Habitat adds:** persistent object identity, task-specific graph slices, execution state, UI state, transactional mutation, and source synchronization.

Reference: https://aider.chat/docs/repomap.html

## 3.2 Serena

Serena demonstrates the value of LSP-backed symbolic navigation and symbol-level editing for coding agents.

**Lesson:** use precise language semantics where available rather than relying only on text chunks.

**What Habitat adds:** LSP is one compiler input, not the workspace itself. Habitat also models build/test/runtime/UI objects and persists a cross-language semantic twin.

Reference: https://github.com/oraios/serena (project location may evolve; verify at implementation time)

## 3.3 SCIP / code intelligence indexes

SCIP provides a language-agnostic schema for source code indexes such as definitions, references, and implementations.

**Lesson:** do not invent a proprietary representation for every language when interoperable semantic index formats already exist.

**What Habitat adds:** normalize SCIP/LSP/Tree-sitter data into a higher-level agent object graph.

Reference: https://github.com/sourcegraph/scip

## 3.4 Tree-sitter

Tree-sitter provides fast incremental parsing, robust syntax trees, and broad language support.

**Lesson:** it is an excellent baseline parser for cold and incremental syntax indexing.

**Boundary:** a syntax tree is not full semantic understanding. Language-specific LSP/SCIP/type analysis is still needed for precision.

Reference: https://tree-sitter.github.io/tree-sitter/

## 3.5 AgentFS

AgentFS shows the value of queryability, snapshots, auditability, and a portable SQLite-backed agent filesystem.

**Lesson:** agent state should be queryable and versioned rather than scattered across opaque process state.

**Boundary:** a POSIX-like file abstraction remains file-centric. Habitat must operate above it at semantic/project/runtime/UI level.

Reference: https://github.com/tursodatabase/agentfs

## 3.6 OpenHands runtime/sandbox

OpenHands demonstrates a clean action/observation boundary for file operations and arbitrary command execution inside a sandbox.

**Lesson:** terminal UI is unnecessary for the agent; execution can be an API action with structured observations.

**What Habitat adds:** task catalog, diagnostics normalization, semantic impact analysis, object-level source manipulation, and UI twin.

Reference: https://docs.openhands.dev/openhands/usage/architecture/runtime

## 3.7 Playwright / Chrome DevTools Protocol / BrowserGym

Playwright can expose ARIA snapshots; Chrome DevTools Protocol exposes DOM, accessibility, layout and style snapshots; BrowserGym turns browser interaction into a formal agent environment.

**Lesson:** web UI can be exposed to agents as structured state instead of only screenshots and coordinates.

**What Habitat adds:** connect rendered UI nodes back to source symbols, components, CSS, routes, tests, console/network failures, and current code transaction.

References:

- https://playwright.dev/docs/aria-snapshots
- https://chromedevtools.github.io/devtools-protocol/tot/DOMSnapshot/
- https://chromedevtools.github.io/devtools-protocol/tot/Accessibility/
- https://github.com/ServiceNow/BrowserGym

## 3.8 Recent repository retrieval research

Recent work continues to show that repository context selection is a first-class problem. Graph-based and partial-dependency retrieval can outperform naive similarity-only or static-global approaches in some code-generation settings, while another recent empirical study reports that pre-indexed semantic search can outperform multi-step deep agentic search for repository QA.

**Lesson:** Habitat should support hybrid retrieval and measure it empirically. It should not hard-code one retrieval ideology.

References:

- DyRetriever / partial dependency graph (2026): https://arxiv.org/abs/2608.01927
- Repository QA semantic search vs deep agentic search (2026): https://arxiv.org/abs/2608.01507
- GraphCoder: https://arxiv.org/abs/2406.07003

---

# 4. The central abstraction: Project Semantic Twin

The workspace has two synchronized realities.

## 4.1 Source Reality

This is the normal project the human can use:

```text
project/
  src/
  tests/
  package.json
  pyproject.toml
  ...
```

It contains executable source bytes and remains compatible with existing tools.

## 4.2 Agent Reality

Habitat compiles Source Reality into a Semantic Twin:

```text
Project
├── Identity
├── Revisions
├── Modules
├── Symbols
├── Relations
├── Types
├── Data/control relationships (where available)
├── Manifests
├── Tasks
├── Tests
├── Diagnostics
├── Runtime services
├── UI surfaces
├── Documentation knowledge
├── Transactions
└── Evidence receipts
```

The two are connected by stable provenance edges.

## 4.3 No semantic object without a source anchor

Example:

```json
{
  "object_id": "sym:python:4f3...",
  "kind": "class",
  "qualified_name": "kernel.memory_service.MemoryService",
  "source": {
    "path": "kernel/memory_service.py",
    "start_byte": 812,
    "end_byte": 6241,
    "source_digest": "..."
  },
  "relations": [...],
  "derived": {...}
}
```

If source changes invalidate the anchor, the semantic object becomes stale until recompiled.

---

# 5. Workspace modes

## 5.1 Linked Folder Mode

Input: an existing folder.

- source folder remains canonical;
- Habitat stores indexes/state in a sidecar workspace database;
- file watcher detects external edits;
- agent transactions atomically update source files;
- source hash conflict detection prevents silent clobbering.

Preferred for normal development.

## 5.2 Managed Import Mode

Input: ZIP or loose files.

- validate archive safety;
- materialize into a managed project root;
- compile semantic twin;
- expose export-as-folder and export-as-ZIP;
- changes are applied to the managed source root immediately.

## 5.3 Future portable workspace bundle

A later portable bundle may package:

- source snapshot or source references;
- semantic DB;
- summaries;
- task catalog;
- test metadata;
- optional runtime caches.

This is not necessary for the first working system and must not block Linked Folder Mode.

---

# 6. Internal architecture

```text
                    INPUT
          folder / ZIP / loose files
                       |
                       v
              +------------------+
              | Source Bridge    |
              | import / watcher |
              +--------+---------+
                       |
                       v
              +------------------+
              | Workspace Compiler|
              +--------+---------+
                       |
          +------------+-------------+
          |            |             |
          v            v             v
    Syntax Layer   Semantic Layer   Text/Docs Layer
    Tree-sitter    LSP / SCIP       FTS + metadata
          |            |             |
          +------------+-------------+
                       |
                       v
              +------------------+
              | Semantic Graph   |
              | + Object Store   |
              +--------+---------+
                       |
           +-----------+------------+
           |                        |
           v                        v
    Context Compiler          Capability Catalog
           |                        |
           +-----------+------------+
                       |
                       v
              +------------------+
              | Agent Protocol   |
              +--------+---------+
                       |
       +---------------+----------------+
       |               |                |
       v               v                v
 Mutation Engine   Execution Engine   UI Surface Engine
       |               |                |
       +---------------+----------------+
                       |
                       v
              +------------------+
              | Verification     |
              | Receipts / State |
              +--------+---------+
                       |
                       v
                Source Reality
```

---

# 7. Workspace Compiler

The compiler is the most important component. The quality of Habitat depends more on compiler/index quality than on prompting.

## 7.1 Stage 1 — Ingestion and classification

For every file:

- canonical path;
- MIME/type classification;
- size;
- digest;
- encoding;
- generated/vendor/build-artifact likelihood;
- language;
- project role hints;
- ignore policy.

Detect project manifests and framework signals:

- `package.json`;
- `pyproject.toml`;
- `requirements.txt`;
- `setup.py/setup.cfg`;
- `pom.xml`;
- Gradle files;
- Makefiles;
- lockfiles;
- test configs;
- frontend configs;
- Docker files only as project configuration, not as a desktop scope expansion.

## 7.2 Stage 2 — Syntax compilation

Use Tree-sitter as the broad language baseline.

Compile:

- syntax tree;
- symbol declarations;
- imports/includes;
- comments/docstrings;
- structural regions;
- references detectable syntactically;
- error nodes.

Store only normalized fields required for later queries, not a redundant dump of every parser object.

## 7.3 Stage 3 — Precise semantic compilation

Use adapters when available:

- LSP;
- SCIP indexes;
- compiler/type-checker APIs;
- language-specific analyzers.

Capture:

- definitions;
- references;
- implementations;
- type relationships;
- rename/refactor capabilities;
- diagnostics;
- call relationships when reliable.

Every relation stores a provenance quality class:

- `compiler_precise`;
- `language_server_precise`;
- `syntax_inferred`;
- `heuristic`;
- `llm_inferred`.

This matters because not all graph edges deserve equal trust.

## 7.4 Stage 4 — Project topology

Derive:

- module/package hierarchy;
- likely entrypoints;
- public APIs;
- framework boundaries;
- test topology;
- configuration topology;
- UI routes/components where detectable;
- build targets.

## 7.5 Stage 5 — Knowledge cards

Create hierarchical cards:

- project card;
- subsystem card;
- module card;
- file card;
- symbol card;
- test card;
- UI component card.

Cards must remain concise and pointer-heavy. They are routing aids, not canonical replacements for source.

## 7.6 Stage 6 — Optional semantic enrichment

LLM-generated enrichment may infer:

- purpose;
- design intent;
- invariants;
- likely ownership/responsibility;
- architectural pattern;
- cross-cutting concerns.

Rules:

1. never required for source correctness;
2. always provenance-bound;
3. marked `inferred`;
4. invalidated when dependencies change;
5. regenerable;
6. cannot override compiler or source evidence.

---

# 8. Persistent object model

Proposed first-class object types:

```text
Project
Revision
File
Region
Symbol
Type
Module
Dependency
Reference
Call
Manifest
Task
Test
Diagnostic
Runtime
Service
Endpoint
UISurface
UIElement
StyleFact
NetworkEvent
ConsoleEvent
Transaction
Patch
Execution
Artifact
Evidence
Summary
ContextSlice
```

## 8.1 Stable identity

Path identity is insufficient because files and symbols can be renamed.

Use a layered identity model:

- persistent workspace UUID;
- revision ID;
- file identity with rename tracking where possible;
- symbol fingerprint from language + qualified name + structural signature;
- source anchor digest;
- relation version.

Stable URIs can look like:

```text
habitat://project/<project-id>
habitat://symbol/<symbol-id>
habitat://test/<test-id>
habitat://run/<run-id>
habitat://ui/<surface-id>/<element-id>
habitat://tx/<transaction-id>
```

The LLM manipulates handles rather than repeatedly reconstructing paths.

---

# 9. Storage design

## 9.1 Recommended initial storage

Use SQLite as the authoritative workspace metadata/state store because it offers:

- portability;
- transactions;
- mature indexing;
- FTS5;
- WAL;
- simple distribution;
- easy inspection and debugging.

Do not store duplicate complete source text by default in the database. Keep source bytes in Source Reality and store digests, ranges, normalized snippets, and content-addressed caches where beneficial.

Suggested layout:

```text
.habitat/
  workspace.sqlite
  blobs/
  cache/
  runs/
  ui/
  transactions/
  locks/
```

The hidden directory may instead live outside the source tree if repository cleanliness is required.

## 9.2 Major tables

Indicative schema groups:

- `workspace_meta`;
- `revisions`;
- `files`;
- `regions`;
- `symbols`;
- `relations`;
- `diagnostics`;
- `manifests`;
- `tasks`;
- `tests`;
- `summaries`;
- `context_slices`;
- `transactions`;
- `patches`;
- `executions`;
- `execution_events`;
- `ui_surfaces`;
- `ui_elements`;
- `ui_relations`;
- `artifacts`;
- `evidence`.

Use FTS5 for searchable text fields and adjacency/index tables for graph expansion.

Do not commit early to a graph database. Benchmark SQLite adjacency queries first. A separate graph engine should be introduced only if measurements show a real bottleneck.

---

# 10. Incremental compilation and invalidation

This is mandatory. Recompiling the whole project after each agent edit defeats the design.

## 10.1 Change event

A change produces:

```text
path
old_digest
new_digest
byte/line delta if known
source = agent | external | generated
transaction_id if applicable
```

## 10.2 Invalidation graph

Invalidate only affected objects:

1. changed file syntax;
2. changed file symbols;
3. direct semantic relations;
4. dependent module summaries;
5. task slices containing invalid objects;
6. affected test mappings;
7. affected UI source mappings;
8. architecture summaries only if dependency thresholds are crossed.

## 10.3 Tree-sitter incremental parse

Use old trees and edit ranges where possible.

## 10.4 LSP incremental notifications

Keep language servers alive per workspace session when worthwhile and update changed documents rather than reinitializing after every action.

## 10.5 Summary invalidation

Every derived summary stores dependency digests. If any dependency digest changes, summary status becomes `stale` before it can be returned as fresh context.

---

# 11. Context Compiler

The Context Compiler is how Habitat converts a huge project into a small cognitive working set.

## 11.1 Input

```json
{
  "task": "Fix login form validation and add regression tests",
  "workspace_revision": "...",
  "budget": {
    "max_objects": 40,
    "max_source_tokens": 12000
  }
}
```

## 11.2 Candidate generation

Use multiple retrieval lanes:

- exact symbol/path/name matches;
- FTS lexical search;
- optional embeddings;
- dependency graph expansion;
- reference/caller/callee graph;
- test graph;
- manifest/task links;
- UI-to-source links;
- recent changed files;
- current diagnostics.

## 11.3 Entry-point selection

Select a small set of likely task entrypoints. Then perform bounded graph expansion rather than sending a global graph to the model.

This combines two useful ideas:

- persistent indexing for low-cost orientation;
- partial task-specific dependency graphs for precise expansion.

## 11.4 Relevance score

A candidate score can combine:

```text
lexical_match
semantic_match
symbol_match
graph_distance
edge_trust
changed_recently
test_relevance
ui_relevance
architecture_importance
source_freshness
summary_confidence
```

Weights must be benchmarked rather than guessed permanently.

## 11.5 Output: Context Slice

Example:

```json
{
  "objective": "...",
  "project": {"id": "...", "revision": "..."},
  "architecture_slice": [...],
  "symbols": [...],
  "contracts": [...],
  "tests": [...],
  "diagnostics": [...],
  "ui": [...],
  "runtime": [...],
  "unknowns": [...],
  "exact_source_handles": [...]
}
```

The agent can request exact source bodies only when required.

## 11.6 Context paging

Treat the workspace as a virtual cognitive address space:

- `resident`: current task-critical objects;
- `warm`: nearby graph objects;
- `cold`: indexed but not loaded;
- `source`: exact bytes retrieved only on demand.

This is analogous to virtual memory, but it must remain explicit and deterministic enough to debug.

---

# 12. Agent-facing protocol

Do not expose hundreds of micro-tools. The protocol should be small and compositional.

## 12.1 Core calls

### `workspace.enter`
Returns project identity, revision, language/framework summary, and available capabilities.

### `workspace.orient`
Compiles the first task slice.

### `workspace.query`
Intent-based retrieval over semantic objects.

### `workspace.inspect`
Returns one object's detailed typed view and optional source body.

### `workspace.related`
Traverses typed relations under explicit depth/budget.

### `workspace.change`
Creates a transaction of semantic/source edits.

### `workspace.run`
Runs a typed build/test/lint/server/custom execution capability.

### `workspace.observe`
Observes runtime or UI semantic state.

### `workspace.verify`
Executes verification obligations against the pending/current revision.

### `workspace.commit`
Commits a verified transaction to Source Reality.

### `workspace.rollback`
Restores previous state for a transaction.

## 12.2 Exact-source escape hatch

The agent may request raw ranges when necessary. Habitat should never prevent exact inspection merely to preserve an abstraction.

---

# 13. Mutation Engine

## 13.1 Preferred mutation order

1. compiler/LSP refactor operation;
2. symbol-level replacement/insertion;
3. AST-aware structured patch;
4. exact text range patch;
5. full-file replacement only as a last resort.

## 13.2 Transaction lifecycle

```text
BEGIN
  capture base revision
  resolve target objects
  validate source anchors
  stage edits
  materialize prospective source
  incremental recompile
  calculate impact
  run required verification
COMMIT or ROLLBACK
```

## 13.3 Conflict rule

If an external editor changes a targeted source object after transaction begin:

- never silently overwrite;
- mark conflict;
- provide old/current/proposed semantic diff;
- rebase or abort.

## 13.4 Semantic diff

Agent-facing diffs should show both:

- exact source patch;
- semantic change summary.

Example:

```text
Changed symbol: AuthService.validateToken
Signature: unchanged
Behavioral branch added: expired-token path
New dependency: TokenClock
Affected callers: 4
Affected tests: 6
Potentially affected UI route: /login
```

---

# 14. Source Bridge and synchronization

## 14.1 Agent -> external source

A committed transaction writes atomically to source files, updates timestamps/digests, and then recompiles affected semantic objects.

## 14.2 External source -> Habitat

A watcher detects changes made by humans/IDEs and updates Habitat.

## 14.3 Revision model

Every successful synchronization creates or advances a workspace revision.

A task slice is always bound to a specific revision.

## 14.4 Export

Managed imports support:

- export folder;
- export ZIP;
- exact manifest of output files and hashes.

---

# 15. Execution Engine — terminal without terminal

The terminal is a human presentation layer. Habitat should treat execution as structured process orchestration.

## 15.1 Task discovery

Compile a task catalog from project configuration.

Examples:

### Node

- npm/pnpm/yarn scripts;
- framework dev/build commands;
- lint/test/typecheck tasks.

### Python

- pytest/unittest discovery;
- pyproject tool configurations;
- package entrypoints;
- linters/type checkers where configured.

### Java

- Maven goals;
- Gradle tasks;
- test targets;
- compile targets.

## 15.2 Generic execution primitive

Avoid shell strings by default.

```json
{
  "program": "python",
  "args": ["-m", "pytest", "tests/test_memory.py", "-q"],
  "cwd_object": "module:root",
  "env_profile": "project",
  "timeout_ms": 120000
}
```

Shell syntax can remain an explicit fallback capability.

## 15.3 ExecutionReceipt

```json
{
  "run_id": "run:...",
  "action": "test.run",
  "exit_code": 1,
  "duration_ms": 8431,
  "summary": {
    "passed": 43,
    "failed": 2,
    "skipped": 1
  },
  "diagnostics": [...],
  "artifacts": [...],
  "changed_files": [],
  "stdout_handle": "blob:...",
  "stderr_handle": "blob:..."
}
```

The agent normally sees normalized diagnostics, not every line of stdout. Raw output is available via a handle.

## 15.4 Output adapters

Build parsers for common tools:

- pytest;
- unittest;
- Jest/Vitest;
- TypeScript compiler;
- ESLint;
- Maven Surefire;
- Gradle test output;
- Java compiler;
- generic compiler errors.

## 15.5 Persistent services

`server.start` returns a service object:

```json
{
  "service_id": "svc:web",
  "state": "ready",
  "endpoints": [{"protocol":"http","port":5173}],
  "logs": "stream:...",
  "health": "healthy"
}
```

No terminal window is required.

---

# 16. Test Intelligence

Tests should be objects, not filenames.

## 16.1 Test discovery

Store:

- framework;
- suite/test identity;
- source location;
- tags/markers;
- runtime estimate;
- last outcome;
- related symbols;
- coverage links where available.

## 16.2 Targeted verification

Given changed symbols, select:

1. directly mapped tests;
2. tests covering callers/dependents;
3. type/build checks;
4. broader regression suite only when justified.

## 16.3 Test graph enrichment

Use runtime coverage opportunistically to improve static mappings.

Never assume static dependency equals behavioral coverage.

---

# 17. AI-native UI Surface

This subsystem is necessary for HTML/front-end work and must not be reduced to screenshots.

## 17.1 UI boot process

Habitat detects likely UI projects and can:

1. identify build/dev command;
2. start a managed service;
3. launch headless Chromium;
4. navigate to target route;
5. create semantic UI snapshot.

## 17.2 UISurface object

A snapshot may contain:

```text
route/url
viewport
accessibility tree
DOM structural projection
interactive elements
visible text
layout rectangles
computed style subset
focus state
form state
console errors
network failures
resource failures
visual screenshot handle
source mappings
```

## 17.3 UIElement object

```json
{
  "ui_id": "ui:login:submit",
  "role": "button",
  "name": "Sign in",
  "visible": true,
  "enabled": true,
  "rect": {"x": 421, "y": 612, "w": 156, "h": 44},
  "styles": {"display":"flex", "font-size":"16px"},
  "dom_path": "...",
  "source_candidates": ["sym:LoginForm", "file:src/login.css"],
  "actions": ["click", "focus"]
}
```

## 17.4 Agent UI actions

```text
ui.query(role="button", name="Sign in")
ui.act(element_id="ui:login:submit", action="click")
ui.fill(element_id="ui:login:email", value="...")
ui.observe(changes_since="snapshot:12")
```

No coordinate guessing is required when semantic identity exists.

## 17.5 Layout reasoning layer

Compute machine-friendly facts such as:

- overlapping rectangles;
- clipped content;
- element outside viewport;
- scroll overflow;
- inconsistent spacing clusters;
- missing accessible names;
- disabled interactive targets;
- text truncation;
- responsive breakpoint changes;
- obvious contrast issues when deterministic calculation is possible.

## 17.6 Pixels remain a secondary oracle

Semantic DOM/layout cannot detect every visual defect. Gradients, images, icon quality, typography rendering, and overall visual balance can require a screenshot/vision model.

Therefore:

> **semantic UI is primary; screenshot vision is a targeted fallback and verification channel.**

---

# 18. UI-to-source mapping

This is where Habitat can become much more powerful than generic browser agents.

For each UI element, attempt to connect runtime state back to source:

- React/Vue/Svelte component hints where tooling permits;
- DOM source maps;
- CSS stylesheet/rule origins;
- route definitions;
- event handler symbols;
- network call symbols;
- test selectors.

Desired flow:

```text
UI button broken
   -> UIElement
   -> event handler
   -> component symbol
   -> source object
   -> related test
   -> transaction
   -> rerender
   -> UI diff
```

This removes repeated manual transitions between browser, source files, and terminal logs.

---

# 19. The agent's persistent “living state”

The phrase “AI lives in the workspace” should be translated into concrete persistent state, not metaphor alone.

Each agent session receives:

```text
workspace revision
active task
resident context objects
open transactions
active executions/services
UI surfaces
recent evidence
known stale objects
unresolved conflicts
budget/limits
```

The model may be stateless between calls, but the Habitat session is not. Object handles remain resolvable and current state can be reconstructed in one small observation.

## 19.1 Session checkpoint

A checkpoint should store references, not huge repeated prompt text.

```json
{
  "revision": "r184",
  "task": "t91",
  "resident": ["sym:a", "sym:b", "test:c"],
  "transaction": "tx:12",
  "service": "svc:web",
  "ui_snapshot": "ui:snap:44"
}
```

---

# 20. Trust and security model for project input

Even though the scope is “only project files”, projects are untrusted inputs.

## 20.1 Import threats

- ZIP path traversal;
- ZIP bombs;
- symlink escapes;
- huge/generated directories;
- malicious build scripts;
- repository prompt injection in documentation/comments;
- poisoned project instructions;
- secrets accidentally indexed;
- commands that attempt host access;
- network exfiltration.

## 20.2 Ingestion rule

Parsing/indexing must not execute project code.

## 20.3 Instruction separation

Project text is source data by default. A dedicated policy file may be recognized only under explicit authority rules. A comment or README cannot promote itself into system authority.

## 20.4 Execution permissions

Execution actions have:

- scope;
- cwd;
- environment allowlist;
- network policy;
- timeout;
- resource budget;
- side-effect declaration;
- changed-file read-back.

The first version may use a local restricted execution provider, but the interface must allow a stronger container/sandbox provider later without changing agent calls.

---

# 21. Applying the Nolane AGI cognitive discipline

The supplied Nolane AGI package contains 56 skills and a runtime doctrine centered on explicit charter, capability diagnosis, context engineering, world models, tool contracts, long-horizon state, evidence, and adversarial completion. Habitat should adopt the useful engineering principles without pretending the package itself proves AGI.

## 21.1 Charter

The immutable product charter for V1:

> Transform normal project inputs into an incrementally compiled agent-native semantic workspace that reduces repository orientation and tool-interface overhead while preserving exact source truth and synchronization.

## 21.2 Capability diagnosis

Required capabilities are separated into:

- deterministic compiler capabilities;
- language semantics capabilities;
- retrieval capabilities;
- mutation capabilities;
- execution capabilities;
- UI observation capabilities;
- synchronization capabilities;
- verification capabilities.

Missing language precision must degrade gracefully to syntax/text methods rather than being guessed.

## 21.3 Context engineering

Keep instruction/policy/source/derived hypothesis/runtime observation separate. Context slices must record omissions, freshness, and source handles.

## 21.4 World model

The workspace is a versioned world model whose state includes source, semantic graph, runtime, UI, and pending mutations.

## 21.5 Tool orchestration

Every execution is typed and produces a read-back receipt.

## 21.6 Long-horizon control

Persistent revisions, task state, transactions, checkpoints and invalidation prevent agents from repeatedly rediscovering the entire project.

## 21.7 Adversarial verification

Benchmarks must compare Habitat against conventional agent tooling under the same model, task, budget and source revision. Do not claim token savings or performance improvements until measured.

---

# 22. API examples

## 22.1 Enter project

```json
workspace.enter({"source":"/projects/app"})
```

Response:

```json
{
  "project":"proj:71",
  "revision":"r1",
  "languages":{"typescript":0.61,"html":0.17,"css":0.12,"other":0.10},
  "frameworks":["react","vite"],
  "capabilities":["symbols.precise","tests.vitest","ui.web","build.vite"]
}
```

## 22.2 Orient task

```json
workspace.orient({
  "task":"The login form freezes after invalid credentials. Fix it and test it."
})
```

Possible response:

```text
Subsystem: authentication/login UI
Relevant symbols:
- LoginForm.submit
- useAuth.login
- AuthClient.signIn
- LoginError
Relevant UI surface: /login
Relevant tests: 4
Current diagnostics: none
Potential runtime path: POST /api/login
Recommended first observations:
- run targeted UI/test suite
- inspect LoginForm.submit and useAuth.login
Unknowns:
- freeze not yet reproduced
```

## 22.3 Inspect without opening file

```json
workspace.inspect({"object":"sym:LoginForm.submit","include_source":"body"})
```

The object response includes only the symbol body, signature, callers/callees, UI links, tests, diagnostics and source pointer.

## 22.4 Run test without terminal

```json
action.run({"capability":"test.run","targets":["test:login-invalid"]})
```

## 22.5 Inspect UI without human browser workflow

```json
ui.observe({"surface":"route:/login","mode":"semantic+layout"})
```

## 22.6 Edit and verify

```json
workspace.change({
  "operations":[
    {"op":"replace_symbol_body","symbol":"sym:LoginForm.submit","body":"..."}
  ]
})
```

Then:

```json
workspace.verify({"transaction":"tx:91","profile":"affected"})
```

---

# 23. Phase/Wave implementation roadmap

The project should be built in bounded waves with a working demonstrator at the end of each major stage.

## Wave 00 — Research freeze and executable contract

Deliverables:

- product charter;
- scope/non-scope;
- threat model;
- benchmark contract;
- object vocabulary;
- agent protocol draft;
- storage decision record;
- language support matrix;
- UI support boundary.

Exit criteria:

- no unresolved contradiction about source authority or sync model;
- benchmark baseline defined before optimization begins.

## Wave 01 — Source Bridge

Build:

- folder linking;
- ZIP safe import;
- loose-file import;
- digests;
- ignore policy;
- external file watcher;
- revision creation;
- atomic write primitives.

Tests:

- path traversal attacks;
- symlink edge cases;
- external edit detection;
- concurrent changes;
- large files;
- invalid encodings;
- deterministic revision metadata.

Exit demo:

Import a mixed project, modify a file externally, see workspace revision update correctly.

## Wave 02 — Syntax Compiler

Build:

- Tree-sitter plugin framework;
- Python;
- JS/TS;
- Java;
- HTML/CSS/JSON/MD;
- symbol and import extraction;
- syntax diagnostics;
- incremental parse.

Exit demo:

Ask for project symbols and structural relationships without opening whole files.

## Wave 03 — Semantic Compiler

Build:

- LSP adapter interface;
- precise adapters for Python, TypeScript/JavaScript, Java;
- optional SCIP import;
- definitions/references/implementations/types;
- semantic provenance grade.

Exit demo:

Inspect a symbol and obtain precise callers/references/implementations across files.

## Wave 04 — Semantic Graph and Object Store

Build:

- object IDs;
- relation schema;
- SQLite store;
- FTS5;
- graph traversal;
- project/module/symbol cards;
- derived-data invalidation.

Exit demo:

One query returns a compact subsystem view over a medium repository.

## Wave 05 — Context Compiler V1

Build:

- task intent parser;
- hybrid candidate retrieval;
- entrypoint ranking;
- bounded graph expansion;
- token/object budget;
- task Context Slice;
- exact-source handles;
- context cache invalidation.

Benchmark immediately against:

- grep/read exploration;
- lexical search only;
- repo-map only;
- semantic search only.

Exit demo:

A new agent enters a project and obtains relevant source/test context in one or two API calls.

## Wave 06 — Agent Protocol V1

Implement stable calls:

- enter;
- orient;
- query;
- inspect;
- related;
- state.

Provide:

- local SDK;
- JSON-RPC or HTTP transport;
- optional MCP adapter, but do not make internal architecture depend on MCP.

Exit demo:

Two different agent clients can use the same workspace without client-specific indexing logic.

## Wave 07 — Transactional Mutation

Build:

- source-anchor validation;
- staged changes;
- symbol-level edits;
- structured patches;
- semantic diff;
- conflict detection;
- atomic commit;
- rollback;
- incremental recompile after transaction.

Exit demo:

Agent changes a symbol; external file updates; semantic graph and affected context update without full re-ingestion.

## Wave 08 — Execution Engine

Build:

- process provider abstraction;
- structured program+args execution;
- task catalog;
- service lifecycle;
- timeouts;
- output/blob capture;
- execution receipts;
- changed-file detection.

Exit demo:

Agent runs a project test/build through typed action calls without a terminal interface.

## Wave 09 — Diagnostics and Test Intelligence

Build:

- pytest adapter;
- Jest/Vitest adapter;
- TypeScript diagnostics;
- Java/Maven/Gradle diagnostics;
- test object model;
- affected-test selection;
- result history.

Exit demo:

After a source edit, Habitat recommends and runs the minimal justified verification set and reports failures structurally.

## Wave 10 — Web UI Surface V1

Build:

- headless Chromium provider;
- server-to-UI connection;
- ARIA snapshot;
- DOM projection;
- layout rectangles;
- visible/interactable state;
- console/network events;
- stable UI element handles;
- semantic click/fill/select actions.

Exit demo:

Agent can understand and operate a sample web UI without coordinate clicks or reading screenshots as the primary channel.

## Wave 11 — UI Source Mapping and Visual Verification

Build:

- DOM/style source hints;
- route/component links;
- UI-to-source graph;
- overlap/clipping/overflow detectors;
- screenshot fallback;
- before/after UI semantic diff.

Exit demo:

Agent detects a UI regression, links it to likely source, patches it, re-renders, and verifies semantic + visual changes.

## Wave 12 — Persistent Habitat State

Build:

- durable agent sessions;
- resident/warm/cold object sets;
- checkpoints;
- active transaction/run/UI state;
- resume protocol;
- stale-handle resolution.

Exit demo:

Agent resumes a task later without redoing repository discovery.

## Wave 13 — Retrieval optimization and adaptive context

Research/implement:

- partial dependency graph retrieval;
- semantic embeddings as optional lane;
- graph ranking;
- dynamic budgets;
- task-class-specific retrieval;
- learned ranking only after sufficient benchmark data.

Ablations:

- no embeddings;
- no graph;
- no LSP;
- no summaries;
- no dynamic expansion;
- no task history.

## Wave 14 — Hardening

Focus:

- malicious archives;
- malicious source instructions;
- huge monorepos;
- generated/vendor trees;
- symlinks;
- watcher races;
- LSP crashes;
- malformed source;
- stale summaries;
- long-running services;
- command timeouts;
- transaction corruption;
- database recovery.

## Wave 15 — Benchmark release

Produce real measurements only.

Compare:

- conventional file/shell agent;
- conventional agent + repo map;
- semantic symbol agent;
- Habitat full stack.

Use same model, same tasks, same token budget, same source snapshot, repeated runs.

## Wave 16 — Packaging V1

Deliver:

- engine;
- SDK;
- protocol specification;
- CLI for humans only;
- workspace inspector GUI for humans only;
- benchmark harness;
- example projects;
- full tests;
- architecture docs;
- migration/export tools.

---

# 24. Benchmark design

The project must prove that it reduces overhead instead of merely moving overhead into a hidden indexer.

## 24.1 Baselines

### Baseline A — traditional tools

Agent has:

- list files;
- read file/range;
- grep/search;
- edit;
- shell;
- screenshot/browser actions.

### Baseline B — traditional + repo map

Adds precomputed repository map.

### Baseline C — semantic symbols

Adds LSP/Serena-like symbol tools.

### Candidate D — Habitat

Full semantic twin/context/action/UI architecture.

## 24.2 Task classes

1. architecture understanding;
2. locate implementation;
3. cross-file bug fix;
4. feature addition;
5. refactor;
6. test failure diagnosis;
7. build failure diagnosis;
8. frontend functional bug;
9. frontend layout bug;
10. mixed backend/frontend task;
11. resume after interruption;
12. external edit during active task.

Projects should include Python, TypeScript, Java, and mixed web stacks.

## 24.3 Core metrics

- task success;
- first-correct-location rate;
- total LLM input tokens;
- source tokens shown to model;
- irrelevant source tokens;
- number of repository-navigation actions;
- number of execution actions;
- latency to first useful hypothesis;
- wall-clock completion time;
- model cost;
- number of retries;
- number of stale-context errors;
- regression rate;
- UI task success;
- resume overhead.

## 24.4 Indexing cost metrics

Report separately:

- cold ingestion time;
- incremental update time;
- storage overhead;
- CPU/memory cost;
- LSP startup cost;
- UI boot cost.

Never hide these costs when claiming token efficiency.

## 24.5 Target hypotheses — not claims

Initial engineering hypotheses to test:

- reduce navigation/read tool calls by at least 50% on repository tasks;
- reduce irrelevant source tokens by at least 60%;
- reduce repeated discovery work after resume by at least 80%;
- preserve or improve task success versus baseline;
- make most targeted test/build output fit into small structured receipts;
- allow common web UI interactions without coordinate actions.

These are acceptance targets to test, not advertised results.

---

# 25. Failure modes and adversarial tests

## 25.1 “Instant understanding” illusion

Failure: summaries sound correct but omit critical code.

Control:

- provenance links;
- confidence;
- graph/source inspection;
- benchmark exactness;
- no summary-as-truth policy.

## 25.2 Stale semantic twin

Failure: source changed but index did not.

Control:

- digests;
- file watcher;
- pre-action source validation;
- freshness status;
- periodic reconciliation scan.

## 25.3 Wrong graph edges

Failure: heuristic relation treated as compiler fact.

Control:

- relation provenance grades;
- confidence-aware retrieval;
- exact compiler/LSP preference.

## 25.4 Context overcompression

Failure: Context Compiler excludes a crucial dependency.

Control:

- uncertainty list;
- bounded expansion;
- agent can request related objects;
- benchmark missed-dependency rate.

## 25.5 Context flooding

Failure: semantic twin becomes a giant prompt dump.

Control:

- strict object/token budgets;
- resident/warm/cold tiers;
- summaries with source handles.

## 25.6 Dangerous execution

Failure: package script modifies outside project or accesses network unexpectedly.

Control:

- execution provider abstraction;
- path/network policies;
- action contract;
- changed-file/read-back receipts;
- stronger sandbox provider before high-trust deployment.

## 25.7 UI semantic blindness

Failure: DOM/ARIA appears valid but visual layout is broken.

Control:

- layout geometry checks;
- screenshot fallback;
- visual regression/vision verification.

## 25.8 UI screenshot overuse

Failure: project falls back to expensive visual reasoning for every UI action.

Control:

- semantic UI default;
- screenshots only for appearance verification or missing semantic state.

## 25.9 Sync conflict

Failure: human and agent edit same code concurrently.

Control:

- base revision;
- source digest check;
- semantic conflict report;
- explicit rebase/abort.

## 25.10 Generated/vendor explosion

Failure: node_modules, build outputs, vendored code dominate indexing.

Control:

- ignore heuristics;
- manifest-aware vendor classification;
- explicit include override;
- storage/token accounting.

---

# 26. Architecture decisions that should remain open until benchmarked

Do **not** lock these prematurely:

1. graph DB vs SQLite adjacency;
2. embedding model/provider;
3. degree of LLM-generated semantic summaries;
4. persistent global graph vs partial dynamic graph balance;
5. exact language-server implementations;
6. local process vs container sandbox default;
7. source map techniques for each frontend framework;
8. whether a portable single-file workspace format is valuable in V1.

Keep adapter boundaries so these choices can change.

---

# 27. Minimum viable research prototype

Before building all waves, create one narrow demonstrator using:

- Python + TypeScript + HTML/CSS;
- SQLite;
- Tree-sitter;
- one Python LSP and one TypeScript LSP;
- FTS5;
- Context Compiler;
- structured subprocess executor;
- Playwright/CDP semantic UI snapshot;
- linked-folder synchronization.

Prototype scenario:

1. import a small full-stack project;
2. ask “where is login validation implemented?”;
3. return exact subsystem/symbol/test map in one orientation response;
4. agent patches code at symbol level;
5. targeted tests run as structured actions;
6. UI service starts without terminal;
7. agent observes `/login` via semantic UI;
8. agent interacts by element IDs;
9. agent verifies the behavior;
10. source files outside Habitat show final changes immediately.

If this scenario does not show a meaningful reduction in token/tool overhead, stop and redesign before scaling the architecture.

---

# 28. Repository structure proposal

```text
nolane-habitat/
├── packages/
│   ├── core/                 # object model, revisions, protocol
│   ├── source-bridge/        # import, sync, watcher
│   ├── compiler/             # compiler orchestration
│   ├── parser-treesitter/    # syntax adapters
│   ├── semantic-lsp/         # LSP adapters
│   ├── semantic-scip/        # SCIP adapter
│   ├── graph/                # relation store/query
│   ├── context-compiler/     # task slices
│   ├── mutation/             # transactions and patches
│   ├── execution/            # process/action engine
│   ├── diagnostics/          # tool output normalization
│   ├── tests-intelligence/   # test graph
│   ├── ui-surface/           # headless browser + semantic UI
│   ├── verification/         # receipts and gates
│   ├── sdk-python/
│   ├── sdk-typescript/
│   └── adapter-mcp/          # optional external adapter
├── schemas/
├── fixtures/
├── benchmarks/
├── adversarial/
├── examples/
├── docs/
└── tools/
```

A monorepo is reasonable because the interfaces must evolve together during alpha.

---

# 29. Required schemas before implementation accelerates

Define machine-readable schemas for:

1. WorkspaceManifest;
2. Revision;
3. SourceObject;
4. SemanticObject;
5. Relation;
6. ContextSlice;
7. Transaction;
8. SemanticPatch;
9. ExecutionAction;
10. ExecutionReceipt;
11. Diagnostic;
12. TestObject;
13. UISurface;
14. UIElement;
15. VerificationReceipt;
16. ConflictRecord.

Version every schema from the start.

---

# 30. Definition of “AI-native” for acceptance

A feature is not AI-native merely because an LLM can call it.

A Habitat capability qualifies as AI-native when it meets most of these criteria:

- returns typed state instead of presentation text;
- has stable object identity;
- minimizes irrelevant bytes/tokens;
- preserves provenance to source truth;
- supports direct machine actions;
- produces explicit postconditions;
- supports incremental updates;
- is resumable;
- exposes uncertainty/staleness;
- avoids forcing the agent to reconstruct relationships that the system can compute deterministically.

Examples:

**Not AI-native:** `shell("npm test") -> 8,000 lines stdout`  
**AI-native:** `test.run(affected) -> 2 failures + diagnostics + raw-log handle`

**Not AI-native:** `read_file("src/app.tsx")` as first step  
**AI-native:** `inspect(sym:LoginForm)` with exact-source body only when needed

**Not AI-native:** screenshot + coordinate click for every UI action  
**AI-native:** semantic UI tree + stable element ID + structured action

---

# 31. Non-negotiable correctness rules

1. Source bytes outrank semantic summaries.
2. No source mutation without revision validation.
3. No derived object without provenance.
4. No stale context silently represented as current.
5. No project code execution during indexing.
6. No shell output treated as success without exit status/read-back.
7. No UI success based only on “page loaded”.
8. No global performance claim without same-model controlled benchmark.
9. No vector-only retrieval architecture.
10. No proprietary semantic layer that prevents exact source export.
11. No requirement for users to abandon normal files.
12. No dependence on a single LLM vendor.

---

# 32. First implementation decisions recommended now

These can be chosen with relatively low regret:

- **Canonical truth:** external/managed source files.
- **Workspace metadata:** SQLite.
- **Text search:** SQLite FTS5 initially.
- **Syntax:** Tree-sitter.
- **Precise semantics:** LSP adapters + optional SCIP.
- **Agent state:** persistent typed objects and revisions.
- **Mutation:** transactions with atomic external writes.
- **Execution interface:** program/args actions + typed receipts, not terminal UI.
- **Web UI:** Playwright/CDP semantic surface + screenshot fallback.
- **Retrieval:** hybrid index + bounded task-specific graph expansion.
- **Transport:** internal API independent from MCP; MCP as an adapter only.
- **Benchmarking:** baseline-first, same-model repeated trials.

---

# 33. Questions deliberately deferred

These are not blockers for starting Wave 00–03:

- final product name;
- cloud service architecture;
- distributed multi-agent coordination;
- remote sandboxes;
- desktop/native GUI support;
- model training;
- cross-machine workspace syncing;
- marketplace/plugin ecosystem.

They should not inflate the first architecture.

---

# 34. Final architectural statement

Nolane Habitat should be understood as a **project cognition substrate**, not an editor and not an operating system.

The project source remains normal and portable. Habitat compiles it into a persistent Semantic Twin and gives AI agents a compact, structured address space over:

```text
code
+ relationships
+ project architecture
+ build/test capabilities
+ execution state
+ web UI state
+ change transactions
+ verification evidence
```

The agent no longer needs to repeatedly reconstruct the project from human-oriented file and terminal interfaces. It can enter the workspace, orient to a task, inspect exact semantic objects, perform typed actions, observe structured results, mutate transactionally, and synchronize the result back to ordinary files.

That is the core product. Every future feature should be rejected if it does not improve one of four properties:

1. **less reconstruction work for the agent;**
2. **more precise project state;**
3. **safer/directer action;**
4. **stronger verification with less irrelevant context.**

---

# 35. Recommended next action

Do not begin with a GUI.

Do not begin with multi-agent orchestration.

Do not begin with a proprietary `.nspace` bundle.

Begin with a **headless research prototype** proving the core loop:

```text
folder/ZIP
 -> compile semantic twin
 -> orient task
 -> inspect symbols
 -> transactional edit
 -> structured test/build action
 -> semantic web UI observation
 -> verification
 -> synchronized source
```

Once this loop is demonstrably more efficient than normal file/shell tooling, expand the workspace rather than expanding the operating-system scope.
