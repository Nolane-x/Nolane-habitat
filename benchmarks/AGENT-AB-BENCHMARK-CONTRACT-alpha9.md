# Habitat Alpha.9 — Same-model A/B Benchmark Contract

This contract exists to prevent retrieval-plumbing metrics from being mislabeled as coding-agent superiority.

## Required paired controls

Each task/repetition must use the same model, model parameters, agent scaffold, repository revision, permissions, time budget, token budget, evaluator, and task prompt. The only intended independent variable is the repository interaction surface: ordinary repository tools versus Habitat.

## Required measurements

- independent task success / regression result;
- input and output tokens from the model provider;
- agent tool calls;
- wall time;
- model-visible exact source bytes;
- authority/backend bytes read when available;
- wrong edits / retries / committed-but-failed states;
- verification outcome and evaluator result.

## Prohibited claims

A deterministic fixture, source-byte benchmark, or Habitat self-test cannot be reported as “same-model A/B”. `agent_ab_harness.py` contains no model and no evaluator; it only enforces paired orchestration and a typed result envelope.
