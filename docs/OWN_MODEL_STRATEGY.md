# Owned Company Model Strategy

## Goal

Build company-owned intelligence that improves from this operating system's approved knowledge, evaluated work, and owner feedback, then progressively reduce dependence on external model APIs. The company owns its data, datasets, evaluation suite, model configuration, and deployment decisions.

This is a staged plan, not a claim that a proprietary foundation model already exists. The current repository has provider-neutral inference interfaces and a learning/evaluation workflow; it does not contain trained model weights.

## What "our own model" should mean

Start with a private, company-specific model stack built around an open-weight base model that we are legally allowed to run and adapt. It can be fine-tuned on our own curated examples and combined with retrieval over owner-approved company knowledge. The base model's original license and notices still apply.

A completely new foundation model trained from random initialization is a different project: it needs very large datasets, specialist infrastructure, GPU time, evaluation, and ongoing maintenance. It is not a sensible zero-budget first step.

## Staged path

### Stage 1 — Own the knowledge and evaluation data

- Keep research candidates untrusted until the owner accepts them.
- Retain source URLs, dates, provenance, agent/run IDs, evaluator version, and owner review decisions.
- Convert successful tasks into training examples only after quality and rights review.
- Exclude credentials, tokens, payment data, private customer conversations, personal data, copyrighted material without rights, and unverified agent claims.
- Maintain train/validation/test splits by time and task family; keep the test set sealed from training.
- Version and hash each dataset export. Never commit private company datasets or model weights to the public repository.

### Stage 2 — Retrieval-first company intelligence

Use the existing accepted-knowledge store as the initial company memory. Improve it with semantic retrieval, deduplication, freshness checks, source quality, and access boundaries before fine-tuning. Retrieval is easier to update and audit than model weights and helps avoid training on stale facts.

### Stage 3 — Build a high-quality training corpus

Create owner-reviewed examples from:
- accepted source-grounded research and corrections;
- successful specialist reports with evidence;
- owner-approved instruction versions and their measured outcomes;
- task-specific expected outputs and evaluation rubrics;
- owner feedback on useful, incomplete, and incorrect results.

Do not treat a high structural score as proof of factual correctness. Human/source review and task-specific evaluation are required.

### Stage 4 — Fine-tune an open-weight model

Select a model only after checking its commercial-use license, hardware requirements, language/task performance, context length, and quantization options. Begin with parameter-efficient fine-tuning (such as LoRA/QLoRA) on a small task-specific dataset. Use a separate held-out benchmark and compare the adapted model against the untouched base model.

The fine-tuning pipeline must be opt-in, reproducible, dataset-versioned, and owner-approved. It must not train on all database contents automatically.

### Stage 5 — Self-host and reduce external dependencies

Package the selected model behind the existing provider-neutral adapter. Test inference latency, memory, reliability, security, and quality on the actual host before routing company work to it. Keep an external provider adapter optional as a temporary fallback only if the owner explicitly enables it; never silently fall back or send private company data to a hosted service.

### Stage 6 — Retire external runtime references

The company can eventually replace runtime dependence on public agent libraries with original, internally maintained role definitions, workflows, and governance. Do not copy third-party material without respecting its license, attribution, and notice requirements. Removing a submodule is not permission to erase obligations attached to code or content already adopted.

## Model lifecycle safeguards

- No training, fine-tuning, model download, GPU rental, or paid inference by default.
- No automatic ingestion of unreviewed research or customer data.
- Dataset lineage, hashes, licenses, exclusions, and splits are recorded.
- Model versions are immutable; promotion requires benchmark results and owner approval.
- Keep the prior model version for rollback.
- Never allow a model to change its own security policy, permissions, or approval boundary.
- The model proposes; the CEO orchestrates; the owner approves consequential changes.

## Practical constraints

The current starting environment is zero-budget and Android-first. It is suitable for designing the data pipeline and testing small inference options, but not for training a competitive foundation model locally. Begin with the data and evaluation pipeline in GitHub; assess actual training hardware only after the company has revenue or free compute is verified.

## Current status

- Available now: accepted knowledge candidates, specialist reports, persisted evaluations, versioned instructions, deterministic regression checks, provider-neutral model adapter.
- Not yet implemented: curated training-example review, dataset export/versioning, semantic retrieval, fine-tuning pipeline, owned model registry/weights, model promotion and rollback.
- No model has been trained by this repository. No third-party provider is required by the architecture, but an actual self-hosted model must still be selected, downloaded, configured, and tested before the system can run without an external inference service.
