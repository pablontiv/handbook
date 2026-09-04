# Model Optimizer Lean Optimization Flow Design

**Date:** 2026-08-20  
**Status:** Approved for implementation  
**Target:** `/Users/pones/.agents/skills/model-optimizer`

## Purpose

`model-optimizer` has two primary user flows:

1. The user adds an API key or subscription, runs the skill, and existing agents receive better models when the newly available models demonstrate an improvement.
2. The user creates an agent, runs the skill, and the new agent receives the most suitable available model.

The skill must discover runtime-local models and agents, derive each agent's needs, evaluate only relevant candidates, propose a mapping, require approval, apply the approved changes, reload the runtime, and verify affected agent paths.

## Non-goals

- Build a general benchmark platform.
- Run complete public benchmark suites locally by default.
- Create a user-facing evidence warehouse or multi-artifact pipeline.
- Assign catalog-only, unauthenticated, or non-responsive models.
- Transfer scores between model-family variants as if they were exact matches.
- Change configuration without explicit approval.

## User Experience

The user invokes the skill without preparing manifests or evaluation files. The skill performs one logical `optimize` flow:

```text
discover models and agents
  -> detect new, changed, missing, or unhealthy routes
  -> derive agent needs
  -> shortlist plausible candidates
  -> reconcile public benchmarks
  -> run exact local role evaluations where needed
  -> show concise before/after mapping
  -> request approval
  -> back up and apply
  -> reload and verify affected agents
```

If nothing relevant changed and current assignments remain healthy, the skill reports a no-op.

The proposal shown to the user contains only the following and never renders config paths, apply targets, cache keys, or artifact plumbing:

- agent;
- current model and effort;
- recommended model and effort;
- concise reason;
- important uncertainty or exclusion;
- estimated operational trade-off when known.

## Discovery and Change Detection

Every run refreshes the existing runtime inventory and live-checks routes that may be retained or assigned. Catalog presence alone is never sufficient.

The lightweight cache stores semantic component fingerprints and evaluation summaries. It does not use the inventory artifact digest for delta detection because that digest includes `created_at` and changes on every refresh. The single state file retains minimal normalized fingerprints for runtime version, model metadata, provider readiness, assignments, and agent definitions. It allows the skill to detect:

- newly ready providers or models;
- new, changed, removed, or unassigned agent definitions;
- model metadata or runtime-version changes;
- expired benchmark or role-evaluation summaries;
- assignments whose provider or model is no longer locally available.

Agent discovery precedes delta calculation. Pi discovery respects `$PI_CODING_AGENT_DIR` or `~/.pi/agent` globally, `.pi/subagents.json` for project profiles, and the documented global/project `agents/` and `subagents/` definition directories. OpenCode discovery merges global/project `opencode.json` agents and global/project Markdown agent directories, including definitions without a model assignment and structured tool/permission maps. Every normalized agent records mode, effective tools and permission rules, mutation authority, definition/assignment/inheritance sources, and the exact internal apply target so apply mutates the same source and scope that inventory analyzed.

A missing or live-failing incumbent triggers remediation even when the user did not add a model or agent.

The first run has no historical delta. It treats current assignments as incumbents and evaluates only plausible challengers rather than the full model-agent Cartesian product.

## Agent Needs

The skill derives requirements directly from each agent definition and configured tools. The analysis covers:

- workload and role archetype;
- required tool allowlist;
- read-only versus mutation authority;
- context and output needs;
- vision requirement;
- reasoning criticality and effort;
- structured-output contract;
- quality, reliability, latency, and cost priority order;
- adversarial-family independence when applicable.

Known evaluation archetypes include mechanical implementation, integration, debugging, architecture, review, routing/delegation, research, scouting, and context building.

If a new agent cannot be matched confidently to an archetype or lacks an objective success criterion, the skill asks the user for a representative task instead of inventing one. After the user responds, the skill creates a bounded, versioned temporary fixture under its evaluation workspace; it never treats arbitrary user project paths or commands as trusted fixtures.

## Candidate Shortlisting

A candidate route is identified by runtime kind/version, exact provider/model ID, and effort or variant. Candidates must first pass mandatory gates:

1. exact runtime-local ID;
2. provider ready;
3. current live response through the target runtime at the proposed effort/variant;
4. required context, output, input modes, and supported options;
5. required safe tool behavior or a separate capability probe for essential custom tools;
6. required adversarial-family independence;
7. any role-specific hard constraint.

The shortlist contains at most four routes per agent, including the incumbent when one exists. It is formed from:

- the healthy incumbent;
- benchmark-supported role matches;
- newly available plausible challengers;
- prior local finalists whose evaluations remain fresh.

High-cost or high-latency models are not shortlisted for a role that explicitly prioritizes low latency unless evidence suggests a material quality advantage. A model is not shortlisted solely because it is newer or more prestigious.

## Benchmark Reconciliation

Public benchmarks are external priors used to shortlist and interpret candidates. They do not establish runtime availability and do not replace exact local validation.

Each usable observation records source, benchmark version, evaluated model identity, harness or agent when known, effort or reasoning mode, metric, date, and URL.

Identity matching uses:

- `EXACT`: same checkpoint or explicitly proven equivalent route;
- `MODEL_EQUIVALENT`: same model checkpoint through another serving route;
- `FAMILY_PROXY`: related family or variant only;
- `ABSENT`: the exact identity has no entry in a successfully queried bounded source set;
- `UNKNOWN`: the provider alias does not disclose enough identity;
- `SOURCE_UNAVAILABLE`: the source could not be queried or verified.

`FAMILY_PROXY` and `UNKNOWN` never receive exact benchmark credit. `SOURCE_UNAVAILABLE` is never rewritten as `ABSENT`. These candidates may remain only through stronger local role evaluation.

## Runtime-Exact, Tool-Confined Role Evaluation

A role evaluation preserves the route identity and role prompt while confining the model to a disposable fixture:

```text
runtime + provider/model + effort + agent system prompt + confined fixture tools + versioned fixture
```

The evaluator does not expose unrestricted host `bash`, ambient extensions, skills, prompt templates, project context, credentials, or arbitrary host paths to an untrusted candidate. Pi starts with `--no-extensions` and explicitly loads only the optimizer's evaluation extension, which replaces requested built-ins with workspace-confined operations and a sandboxed allowlisted test runner. OpenCode starts with an isolated configuration root, deny-all defaults, `external_directory: deny`, confined file operations, and candidate `bash` denied; the trusted evaluator runs manifest tests afterward through the process sandbox. Effective runtime configuration is verified before model launch.

Custom production tools are capability-probed separately. If a custom tool is essential to the role and cannot be verified without exposing the host, the route is `ABSTAIN`, not approximately certified. Candidate-generated code is executed only through an available process sandbox with a scrubbed environment and network denial; if no supported sandbox backend exists, mutation/code-execution fixtures are unavailable and the optimizer abstains. Read-only static fixtures may still run with confined file access.

The evaluator request carries the validated model record, complete route key, agent contract, derived role requirements, trusted prepared-workspace token, and an immutable fixture policy containing identity/version, manifest digest, grader ID, allowed paths, stable command IDs/argv, sandbox requirement, and fresh capability-probe attestations. Request construction fails if these values disagree with the prepared workspace marker. Transient tool arguments are reduced to bounded audit facts and then discarded. Evaluation records:

- objective task success and a bounded `0.0..1.0` role score;
- required tests or grader checks;
- instruction and output-contract compliance;
- bounded command ID, exit status, elapsed time, and sandbox backend for required tests; changed paths; outside-workspace attempts; and unauthorized tools;
- elapsed time;
- token usage and metered cost when available;
- human intervention or inconclusive behavior.

Graders validate semantics rather than brittle formatting. For example, `client.py:8`, `client.py:4-9`, and `client.py:5,8` are all valid evidence for line 8.

The adaptive policy stores per-fixture summaries with bounded per-run latency, reliability, intervention, and metered-cost observations rather than unauditable aggregates:

- every final assignment receives at least one runtime-exact, tool-confined local role evaluation;
- `FAMILY_PROXY`, `ABSENT`, `UNKNOWN`, `SOURCE_UNAVAILABLE`, or contradictory evidence requires fuller local evaluation;
- an initial quality tie returns `NEEDS_MORE_EVIDENCE` and runs another compatible discriminating fixture; the shipped mechanical and debugger archetypes each have two independent trusted fixtures;
- inconclusive evaluation infrastructure does not penalize the model;
- unresolved evidence causes abstention or retention of a healthy incumbent.

## Selection Rules

Selection is gate-first, not a universal blended score.

1. Exclude candidates that fail mandatory requirements.
2. Compare objective role-evaluation quality and contract compliance.
3. Use compatible public benchmark evidence as support.
4. Compare operational reliability and intervention.
5. Apply the priority order derived from the agent definition, such as latency before cost.

A challenger replaces a healthy incumbent only after demonstrating a material advantage. By default, material means either a higher mandatory quality/contract tier, or a role-score improvement of at least `0.10` on the `0.0..1.0` scale on each of two compatible fixtures. When quality is tied, the challenger must improve the agent's highest-priority operational metric by at least `20%` across at least two comparable per-run observations without reducing reliability or increasing intervention. Otherwise the incumbent remains to avoid routing churn.

A new agent receives the best eligible finalist. If a first fixture cannot separate finalists, the decision is `NEEDS_MORE_EVIDENCE`; if no candidate ultimately has sufficient evidence, the skill reports `ABSTAIN` and explains what is missing.

For adversarial reviewer/worker pairs, different providers serving the same model family do not satisfy independence. Different live model families are required when enough eligible families exist.

## Lightweight Cache

The cache is one internal optimization file, not a user-facing artifact system. It stores semantic inventory/agent fingerprints plus normalized benchmark and role-evaluation summaries; it never stores prompts, model responses, tool arguments, API keys, credentials, or source code.

Evaluation keys include:

```text
runtime kind and version
provider/model exact ID
effort or variant
agent-definition hash
tool-allowlist hash
fixture version
model-metadata fingerprint
```

Benchmark summaries also record source identity, harness/agent, model identity, effort/reasoning mode, metric, and observation date. Live health is always refreshed. Cached benchmark and role-evaluation summaries expire after seven days and invalidate immediately when any key component changes. Ambiguous provider aliases therefore cannot retain evidence indefinitely under an unchanged friendly name.

The cache uses a validated absolute cache path, atomic locked read-modify-write, and strict JSON. It cannot resolve inside Pi/OpenCode configuration trees. Cache failure degrades to fresh evaluation and never blocks optimization.

## Approval, Apply, and Rollback

The evidence helper remains read-only. After presenting the complete proposal, the skill stops for explicit approval.

On approval, the skill constructs an internal change payload with the exact apply target and source digest, then:

1. creates a timestamped backup of the runtime-native configuration;
2. modifies only affected agent assignments and supported options;
3. validates configuration syntax;
4. performs the required hot reload, `/reload`, restart, or new-session transition;
5. invokes each affected agent path with a small post-reload check.

The internal approved-change payload—not the rendered proposal—carries the exact source scope and configuration target discovered for every affected agent. If write, validation, reload, or post-reload verification fails, the skill atomically restores the backup, validates it, reloads or restarts the runtime again, and verifies the restored agent paths before reporting rollback success. It never claims success from restored disk bytes alone or from a direct model probe when the configured agent path was not verified.

## Failure Behavior

- One unavailable provider excludes its models without aborting unrelated evaluation.
- An unavailable benchmark source triggers local evaluation and is reported as unavailable, not absent.
- A stale cache entry is ignored.
- A fixture or grader failure marks that result inconclusive rather than penalizing the model.
- Unsupported effort or options are omitted from configuration.
- A quota or rate-limit failure is preserved as operational evidence and never converted into a model-quality failure.
- No eligible candidate produces `ABSTAIN`, not a speculative assignment.

## Implementation Boundaries

The current `inventory` and `check` helper commands and their digest-bound JSON remain internal evidence mechanisms. The implementation must not introduce the previously proposed collection of separate user-facing manifests and evidence artifacts.

The skill instructions orchestrate the user flow. Focused helper modules may support:

- agent requirement extraction and hashing;
- shortlist and gate evaluation;
- runtime-exact route and agent discovery;
- confined role-eval execution and bounded tool audit;
- semantic grading and adaptive evidence collection;
- cache loading and atomic updates;
- concise proposal rendering.

Configuration mutation remains outside the read-only evidence helper and occurs only through the approved skill apply step.

## Testing Strategy

Implementation follows test-driven development and preserves the existing suite.

Required coverage:

1. Semantic delta detection for new providers, models, agents, and missing incumbents without timestamp churn.
2. Runtime-specific discovery of assigned and unassigned Pi/OpenCode agents with exact source scope.
3. Identity classification with exact, equivalent, proxy, absent, unknown, and unavailable-source cases.
4. Gate-first shortlisting capped at four complete routes, including incumbent effort/variant.
5. Pi/OpenCode isolation: no ambient extensions/config, confined paths/commands, scrubbed test environment, and fail-closed sandbox availability.
6. Bounded tool audit and semantic graders accepting equivalent evidence formats while rejecting incorrect diagnoses.
7. Cache keying, benchmark/evaluation seven-day expiry, semantic invalidation, locked atomic writes, and corruption fallback.
8. Adaptive behavior: `NEEDS_MORE_EVIDENCE`, defined material advantage, and incumbent retention on unresolved ties.
9. New-agent behavior: select an eligible finalist or abstain.
10. Approval gate, exact-scope backup/edit, reload verification, and runtime-verified rollback.
11. Pressure scenarios for urgency, aliases, stale evidence, partial remaps, isolation failure, and rollback failure.

The two validated pilot scenarios become regression fixtures:

- mechanical implementation: GPT-5.4 mini remains incumbent when challengers do not demonstrate improvement;
- read-only regression triage: candidates must identify the millisecond-to-second conversion defect without modifying tracked files.

## Success Criteria

The design is successful when:

- adding a provider or model causes only relevant agents and candidates to be reconsidered;
- adding an agent produces a justified mapping without evaluating every available model;
- unavailable or unhealthy current assignments are surfaced automatically;
- every proposed route is live and locally validated with its exact model/effort/prompt under confined required tools, with essential custom capabilities proven separately;
- benchmark identity uncertainty remains explicit;
- healthy incumbents are stable under ties;
- no configuration changes occur before approval;
- applied mappings pass post-reload agent-path checks or roll back automatically;
- the normal user sees a concise recommendation, not internal evidence plumbing.
