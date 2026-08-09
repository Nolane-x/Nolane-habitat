# Same-model Agent A/B Benchmark Contract — alpha.4

Alpha.4 ships deterministic access/instrumentation harnesses, **not an AI capability result**. A future claim that Habitat improves an agent is admissible only under this contract.

## Arms

- **A — conventional project tools:** same model receives normal file listing/search/read plus equivalent typed execution/test/UI evidence where reasonably available.
- **B — Habitat:** same model receives Habitat protocol methods. Do not secretly add stronger evaluator hints or unrestricted shell/file dumps to either arm.

## Required controls

Use the exact same:

- model/provider/version;
- system instructions and task prompt;
- repository snapshot and dependency state;
- hidden evaluator/test oracle;
- retry/recovery policy;
- token and wall-clock ceiling;
- external network state;
- hardware class when latency is reported.

Randomize arm order. Use hidden/mutated tasks and at least three repeated runs per task/arm; more repetitions are required for noisy tasks. Preserve raw trajectories, protocol/process receipts and evaluator outcomes.

## Required cost accounting

Separate:

1. one-time Habitat ingest/index cost;
2. warm incremental maintenance cost;
3. per-task agent interaction cost.

Disclose amortization assumptions. Do not hide preprocessing in arm B while charging every read to arm A.

## Instrumentation

Alpha.4 trace sessions can report:

- protocol call count/method distribution;
- request/response bytes;
- exact-source bytes returned;
- measured protocol-call durations.

These fields are useful plumbing evidence but are **not tokens**. Model-provider token counts must be collected from the same authoritative provider accounting in both arms.

## Outcome metrics

Report at minimum:

- task success;
- regression-free success;
- hidden-test success;
- input/output/cached tokens where authoritative;
- exact-source bytes requested;
- tool/API calls;
- wall time;
- verification runs;
- stale-context/resume failures;
- intervention count;
- recovery success;
- monetary cost when comparable;
- tail failures and per-task distribution.

Do not collapse everything into one headline average.

## Anti-gaming / evaluator integrity

- keep hidden or mutated evaluator cases out of agent-accessible source;
- detect test/evaluator tampering;
- do not count editing the grader as task completion;
- retain failed trajectories rather than selectively discarding them;
- document any arm-specific unavailable capability;
- quarantine results if provider/runtime behavior changes mid-experiment.

## Admission rule

No “Habitat improves coding agents / reduces token use by X%” claim is admitted unless the same-model experiment satisfies the controls above and its raw evidence is preserved. Deterministic alpha.4 plumbing reports can support architecture debugging only.
