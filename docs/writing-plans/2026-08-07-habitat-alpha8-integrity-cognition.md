# Alpha.8 Writing / Implementation Plan — Integrity Before Intelligence

## Input evidence
External alpha.6 audit containing 59 findings. Alpha.7 is treated as the current baseline, so every finding must first be re-probed rather than assumed present.

## Charter
Upgrade one release level only after converting the highest-risk findings into falsifiable invariants and regression evidence. Do not spend the checkpoint on broad language/framework expansion while world-truth and side-effect boundaries remain porous.

## Protected invariants
1. Canonical source is authority; Semantic Twin may be stale only when the staleness is explicitly visible.
2. Consequential operations validate all identifiers/state-machine preconditions before side effects.
3. A high-level agent operation distinguishes `NOT_COMMITTED` from `COMMITTED_VERIFICATION_ERROR`.
4. Context I/O accounting never equates bytes shown to the model with bytes read from authority.
5. Weak/derived graph evidence cannot become exact merely through propagation or feedback.
6. Persistent state cannot silently cross workspace identity.
7. Unsandboxed execution is reported as unsandboxed.

## Hypotheses and discriminating probes

### H1 — metadata-assisted reconcile can protect ordinary perception without full hashing on POSIX
Probe: modify content with identical size, restore mtime, call `reconcile()`.
Kill criterion: unchanged revision / no changed path.
Windows boundary: use deep content reconcile until native journal support exists.

### H2 — Context VM can virtualize authority I/O, not only model exposure
Probe: >1 MB source, target symbol near EOF, single page fault.
Kill criterion: backend reads whole file.
Metric: report both agent-visible and authority-read bytes.

### H3 — cognitive feedback must be revision-valid
Probe: submit feedback from R1 after source advances to R2.
Kill criterion: accepted feedback.

### H4 — episode is an enforced state machine
Probes: missing episode stage/verify, stale context episode start, commit after completed episode.
Kill criterion: any source/run/transaction side effect occurs before rejection.

### H5 — mutation preserves unrelated file semantics and survives process interruption
Probes: CRLF + 0755 one-line edit; simulated crash in applying journal; restart recovery.
Kill criterion: LF normalization, mode loss, partially applied local transaction after startup.

### H6 — source policy prevents accidental private/generated/self-state ingestion
Probes: `.gitignore`, `.habitatignore`, Habitat state inside project, managed-file workspace reuse.

### H7 — execution evidence is bounded and provenance-rich
Probes: >64 KiB output plus secret; verify capture does not retain all output in Python memory and receipt reports totals/redaction/environment.

### H8 — hypothesis management can be explicit without pretending confidence is probability
Probe: hypothesis → experiment → result → belief update; ensure revision binding and explicit confidence semantics.

## Milestones
M1 audit disposition; M2 source/perception integrity; M3 sparse range I/O; M4 episode enforcement; M5 WAL mutation/fidelity; M6 source policy/identity; M7 execution accounting/safety posture; M8 indexed multilingual retrieval; M9 MCP error semantics; M10 hypothesis/experiment layer; M11 full historical regression; M12 AGI-ZIP stress; M13 packaging/admission.

## Deferred by evidence, not forgotten
OS sandbox, enterprise secret-state governance, distributed multi-agent concurrency, remote authoritative change streams, universal language precision, full program causal model, same-model A/B.
