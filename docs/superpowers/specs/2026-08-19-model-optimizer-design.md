# Portable model optimization with runtime-local evidence

**Status:** Approved for implementation planning
**Date:** 2026-08-19
**Repository:** `pablontiv/skills`
**Skill:** `skills/model-optimizer/`

`model-optimizer` is a portable Agent Skill for assigning models to agents in Pi and OpenCode. It treats each runtime's effective local state and live responses as assignment authority, uses online sources only to enrich locally viable candidates, and requires human approval before configuration changes. A standard-library Python helper gathers and normalizes evidence; it never selects models or mutates runtime configuration.

## Decision summary

| Topic | Decision |
|---|---|
| Initial runtimes | Pi and OpenCode |
| Source of truth | This repository's `skills/model-optimizer/` |
| Architecture | Reasoning skill plus read-only evidence helper |
| Runtime | Python 3.11+, standard library only |
| Helper commands | `inventory` and `check` |
| Assignment authority | Exact runtime-local ID with ready auth and live PASS |
| Online sources | Metadata only; never candidate authority |
| Configuration apply | Outside the helper, after explicit human approval |
| Existing global skill | Migration input after baseline RED; not a dependency |
| Distribution | Self-contained Agent Skill; no sibling-skill dependency |

## Problem

Model catalogs, cached metadata, advisor recommendations, and runtime configuration answer different questions. A model may appear in a catalog but lack credentials, resolve under a different exact ID, fail through the selected runtime, ignore a requested effort level, or disappear after a provider change. Static benchmark-first routing therefore produces assignments that look strong but cannot run.

Model optimization also involves judgment that should not be hidden in a script: role requirements, author-versus-auditor independence, cost-per-solved-task, quota pressure, visual needs, prompt caching, and reload semantics. The process needs deterministic evidence collection without delegating final selection or mutation authority to automation.

## Goals

1. Detect whether Pi or OpenCode is the selected runtime before reading runtime-specific state.
2. Capture current assignments, locally visible model IDs, provider readiness, and metadata without exposing credentials.
3. Live-check exact candidate IDs through the selected runtime with bounded timeouts.
4. Distinguish catalog-local, ready-local, and live-local model sets.
5. Treat broken current assignments as required remap findings without stopping the full analysis.
6. Derive model choices from explicit workload criteria before considering model names.
7. Preserve independent model-family bias for implementer/auditor and other adversarial pairs.
8. Reconcile official documentation and advisors against runtime-local evidence.
9. Present before/after assignments, effort options, exclusions, and reload requirements before asking for approval.
10. Keep configuration writes human-approved and runtime-native.
11. Support macOS, Linux, and Windows with no hard-coded user paths.
12. Test both the helper behavior and the skill's decision discipline with RED/GREEN/REFACTOR.

## Non-goals

Version 1 will not:

- automatically select a model from benchmark scores;
- write Pi or OpenCode configuration;
- refresh or mint credentials;
- install runtimes, providers, models, or dependencies;
- query online advisors from the Python helper;
- provide automatic fallback, retry routing, or runtime model switching;
- infer that two serving providers represent different model families;
- claim cache hits, vision behavior, or tool-call quality from catalog metadata alone;
- support runtimes other than Pi and OpenCode;
- depend on another skill in this repository;
- hard-code the path of a separately installed skill.

## Repository layout

```text
skills/model-optimizer/
├── SKILL.md
├── scripts/
│   └── model_optimizer.py
├── helper/
│   ├── __init__.py
│   ├── models.py
│   ├── runner.py
│   ├── artifacts.py
│   └── adapters/
│       ├── __init__.py
│       ├── pi.py
│       └── opencode.py
├── references/
│   └── contracts.md
└── tests/
    ├── __init__.py
    ├── fixtures/
    │   ├── pi/
    │   └── opencode/
    ├── support.py
    ├── test_artifacts.py
    ├── test_cli.py
    ├── test_opencode.py
    └── test_pi.py
```

The installed skill is self-contained. `scripts/model_optimizer.py` is the only executable entrypoint and imports only sibling modules plus the Python standard library.

## Core evidence model

The skill uses three nested sets:

| Set | Meaning |
|---|---|
| `catalog_local` | Exact IDs currently advertised by the selected runtime |
| `ready_local` | Catalog-local IDs whose provider credential path is ready |
| `live_local` | Ready-local candidate IDs that return the required minimal response through the runtime |

Only `live_local` PASS models are assignable. `FAIL` and `HANG` are terminal exclusions for the current optimization run. A lower-ranked PASS model is preferred over any catalog-only or live-failing model.

Evidence precedence is fixed:

1. exact live response through the selected runtime;
2. runtime auth readiness and effective local listing;
3. runtime-local configuration and cache metadata;
4. official provider/model documentation;
5. model advisors and market catalogs;
6. stale static references.

A weaker source may enrich a stronger source but may not override it. Disagreements are preserved in the report, and the stronger local value is used for configuration.

## User flow

### 1. Runtime resolution

The skill resolves runtime intent from the user and active harness. Pi is selected for Pi, Gentleman, Superpowers/SDD subagents, or generic optimization inside a Pi session. OpenCode is selected only from explicit OpenCode context. If both remain plausible, the skill asks one concise question and performs no runtime-specific reads first.

### 2. Inventory

```bash
python scripts/model_optimizer.py inventory \
  --runtime auto \
  --output inventory.json
```

`inventory` is local and read-only. It records:

- runtime identity and version;
- cwd and discovery sources;
- current assignments and options;
- locally listed exact model IDs;
- provider readiness;
- local context, output, reasoning, input-mode, cache, and cost metadata when available;
- exclusions and bounded reason codes.

The `inventory` orchestration also invokes the adapter's reload-semantics hook, but `model-optimizer.inventory/v1` does not serialize its result. The reasoning/report layer must state the runtime-native hot-reload, `/reload`, restart, or new-session semantics. Inventory never writes runtime state or prints credential material.

### 3. Criteria and candidate selection

The agent classifies every role before naming a model:

- context and output needs;
- reasoning criticality;
- tool and terminal use;
- visual or multimodal needs;
- speed, token cost, quotas, and turn-count risk;
- cache usefulness for stable prompts;
- runtime role;
- adversarial relationship;
- supported effort, verbosity, temperature, and step options.

The agent chooses candidate IDs only from `ready_local`. Current assignments are included even when broken so the report can explain required remaps.

### 4. Live checks

```bash
python scripts/model_optimizer.py check \
  --inventory inventory.json \
  --model provider/model \
  --effort minimal \
  --timeout 60 \
  --output health.json
```

`check` invokes the selected runtime's normal non-interactive model path. PASS requires exit code zero and the requested sentinel in the response. Nonzero exit, missing sentinel, or empty output is FAIL. A deadline breach is HANG; the helper terminates the process and records a bounded reason.

The command accepts repeated `--model` values but applies a small adapter-defined concurrency cap. It never silently retries a failed model under an alias or fallback.

### 5. Online enrichment

After local discovery and live checks, the agent may use official documentation, a model advisor, or a market catalog to enrich overlapping live candidates with benchmarks, release information, modality details, cache behavior, pricing, and quotas.

Advisor-only IDs remain excluded. When an online source and the runtime disagree about ID, context, output, effort support, or modalities, the report shows the mismatch and uses the runtime value.

### 6. Proposed mapping and approval

The skill outputs:

- target runtime and discovery sources;
- current assignment snapshot;
- catalog-local, ready-local, and live-local sets;
- PASS/FAIL/HANG table with elapsed times and bounded causes;
- explicit exclusions;
- agent workload analysis;
- proposed exact model and supported options per role;
- before/after configuration snapshot;
- adversarial-family verification;
- actual configuration fields versus prompt-level intent;
- apply and reload requirements.

The skill then stops for explicit human approval. It does not interpret a request to analyze or optimize as permission to edit configuration.

### 7. Apply and post-reload confirmation

After approval, the agent edits configuration using normal runtime tools, validates syntax/schema, states whether hot reload, `/reload`, restart, or a new session is required, and confirms affected agent paths after reload. The helper remains read-only throughout.

## Helper architecture

### Domain records

`helper/models.py` defines immutable records and enums for:

- `RuntimeKind` (`pi`, `opencode`);
- `ProviderReadiness` (`ready`, `not_ready`, `unknown`);
- `HealthStatus` (`PASS`, `FAIL`, `HANG`);
- current assignments and runtime options;
- model metadata and evidence provenance;
- exclusions and stable reason codes;
- inventory and health artifacts.

All records expose explicit JSON serialization. Artifact schemas are versioned and reject unknown required-enum values when read back.

### Command runner

`helper/runner.py` invokes argument arrays without a shell. It provides:

```text
run(argv, timeout, cwd, env_overlay) -> CompletedCommand
```

The runner:

- inherits the current process environment so runtime-native credential resolution still works, applies only explicit controlled overrides, and never serializes the environment;
- captures bounded stdout and stderr;
- terminates timed-out process trees using platform-appropriate standard-library APIs;
- returns elapsed milliseconds and exit status;
- redacts secrets before returning or serializing output;
- supports a fake implementation in tests.

The helper never accepts arbitrary shell fragments.

### Runtime adapter contract

Each adapter implements:

```text
detect(context) -> detection evidence
snapshot(context) -> current assignments
list_models(context) -> catalog-local records
check_readiness(providers, context) -> provider readiness
live_check(model_record, effort, sentinel, timeout, context) -> health record
reload_semantics(context) -> structured guidance
```

Adapters own runtime command shapes and parsing. Shared artifact, redaction, timeout, and serialization logic stays outside them.

## Pi adapter

The Pi adapter uses only Pi-local evidence:

1. capture `PI_PROVIDER`, `PI_MODEL`, `PI_REASONING_LEVEL`, cwd, and `pi --version`;
2. parse `pi --list-models` for exact advertised IDs and display metadata;
3. inspect `~/.pi/agent/settings.json`, `models-store.json`, `models.json`, and matching global/project `subagents.json` when present, extracting only structural model/profile fields and dropping secret-valued fields before records leave the adapter;
4. call `pi auth check --provider <provider> --json --no-refresh` for represented providers;
5. live-check with:

```bash
pi --no-session -p \
  --no-tools \
  --model provider/model \
  --thinking minimal \
  "Reply exactly: PONG"
```

The adapter never reads credential values or invokes `pi auth ... --credentials`. It redacts config values whose keys indicate tokens, keys, secrets, passwords, cookies, authorization, or credentials.

Pi model/profile changes require the semantics reported by the installed Pi/subagent version. Subagent markdown or `subagents.json` changes are reported as requiring `/reload` or restart unless the effective runtime explicitly proves otherwise.

## OpenCode adapter

The OpenCode adapter uses only OpenCode-local evidence:

1. capture `opencode --version`, cwd, and selected configuration path;
2. parse `opencode auth list` for provider readiness without token material;
3. parse `opencode models --verbose`, whose output is an exact model ID followed by one JSON metadata object, for servable IDs, family, limits, cost, modalities, tool calling, cache metadata, and supported variants;
4. read `opencode.json` for current agent assignments and supported options;
5. live-check with JSON event output and a variant only when the model metadata declares it:

```bash
opencode run \
  --format json \
  --model provider/model \
  --variant high \
  "Reply exactly: PONG"
```

On launch failure, the adapter may inspect a bounded tail of the documented OpenCode log for reason codes such as model-not-found or undefined model. It redacts secrets and never treats helper scripts or external catalogs as stronger than `opencode models` plus the live response.

OpenCode configuration changes are reported as requiring restart unless the installed runtime proves another behavior.

## Artifact contracts

### Inventory

Canonical UTF-8 JSON uses schema `model-optimizer.inventory/v1`. Required top-level fields are:

```json
{
  "schema": "model-optimizer.inventory/v1",
  "created_at": "RFC3339 UTC",
  "runtime": {"kind": "pi", "version": "...", "cwd": "..."},
  "sources": [],
  "current_assignments": [],
  "catalog_local": [],
  "provider_readiness": [],
  "exclusions": [],
  "warnings": [],
  "digest": "sha256:..."
}
```

`ready_local` is derived from catalog IDs and provider readiness rather than duplicated as mutable state. The inventory digest is serialized in v1 and is computed over canonical JSON with `digest` blanked.

### Health

Canonical UTF-8 JSON uses schema `model-optimizer.health/v1`:

```json
{
  "schema": "model-optimizer.health/v1",
  "created_at": "RFC3339 UTC",
  "inventory_digest": "sha256:...",
  "checks": [
    {
      "model": "provider/model",
      "effort": "minimal",
      "status": "PASS",
      "elapsed_ms": 1234,
      "reason_code": "live_sentinel_matched",
      "response_matched": true,
      "detail": ""
    }
  ]
}
```

The inventory digest binds health evidence to the local snapshot it tested. It is evidence, not authorization to mutate configuration. A changed inventory requires new health evidence before apply.

## Error handling

Stable reason-code families are:

- `runtime_*` for missing, ambiguous, or unsupported runtime detection;
- `inventory_*` for command, parse, config, or source failures;
- `auth_*` for ready, missing, expired, or unknown credential paths;
- `live_*` for sentinel match, empty output, nonzero exit, unsupported model, or timeout;
- `artifact_*` for schema, digest, or serialization errors;
- `redaction_*` for output that cannot be proven safe to persist.

A partial inventory is written only when every missing surface is represented by a warning or exclusion. Silent omission is forbidden. If output redaction cannot prove that a captured diagnostic is safe, the helper persists only the stable reason code.

## Security and privacy

- Inventory and check never mutate runtime configuration.
- Credential commands use readiness-only modes.
- API keys, OAuth tokens, authorization headers, cookies, passwords, and secret environment values are never serialized.
- Error excerpts are bounded and redacted before persistence.
- Commands use argument arrays and no shell.
- Config paths are resolved from runtime conventions and explicit test overrides, never personal hard-coded paths.
- Tests operate in temporary homes and fake PATH directories.
- Production rejects test-only home and executable overrides unless an explicit test-mode environment flag is present.
- Health checks may consume provider quota; the skill presents the candidate set and expected call count before broad checks.
- The helper performs no market or advisor network calls.

## Model assignment policy

The skill applies these mandatory rules:

1. Selection criteria precede model names.
2. Only exact live-local PASS IDs are assignable.
3. Current FAIL/HANG assignments become required remaps.
4. Runtime-local evidence wins all discovery conflicts.
5. Model family, not serving provider, defines adversarial independence.
6. Implementer and terminal auditor use different model families when enough PASS families exist.
7. Review lenses and judges use different families when the live set permits it.
8. Cheap administrative phases use fast low-cost models; critical implementation and verification justify higher effort.
9. Effort and options are included only when the runtime/provider supports them. Unsupported effort is expressed as prompt-level intent, not invented configuration.
10. Catalog cache metadata is labeled as capability/pricing metadata until runtime usage proves a hit.
11. Vision is selected only for roles with visual inputs; modality alone is not a quality score.
12. Quotas and rate limits are reported separately from token pricing.
13. The user sees analysis and before/after state before any apply.
14. Post-reload agent-path confirmation is required before claiming end-to-end success.

## Skill authoring and test strategy

Writing the skill follows `writing-skills` and strict RED/GREEN/REFACTOR.

### RED: baseline behavior without the skill

Fresh-context agents receive pressure scenarios that tempt them to:

1. recommend an advisor-only model absent from the runtime;
2. edit profiles before live checks because the user asks for speed;
3. repair one broken assignment and stop instead of completing the mapping;
4. treat two providers serving the same model family as adversarial independence;
5. invent unsupported effort fields;
6. claim completion before reload and agent-path verification;
7. expose credential material while diagnosing auth.

The test record captures exact choices and rationalizations. A scenario whose no-guidance control already behaves correctly is not used to justify new guidance.

### GREEN: minimal skill

`SKILL.md` contains only the guidance required to correct observed baseline failures, plus concise runtime adapter references and output contracts. Its description starts with `Use when...`, contains trigger conditions rather than workflow summary, and stays within Agent Skills frontmatter limits.

The same scenarios run with the skill explicitly loaded. Success requires runtime-first discovery, exact live checks, complete remap analysis, independent-family mapping, approval before apply, and correct reload guidance.

### REFACTOR: close observed loopholes

New rationalizations are added only after a failing test demonstrates them. Wording micro-tests include a no-guidance control, at least five fresh-context repetitions per variant, and manual review of every match before full pressure scenarios.

### Helper tests

`unittest` tests use fake executables, temporary homes, and no network. Required groups cover:

- unique and ambiguous runtime detection;
- Pi and OpenCode inventory parsing;
- current assignment extraction;
- provider ready, not-ready, and unknown states;
- exact ID preservation;
- PASS, FAIL, and HANG;
- timeout termination;
- partial discovery with explicit warnings;
- secret redaction and bounded diagnostics;
- stable canonical JSON and inventory digest binding;
- rejection of arbitrary shell input;
- proof that no helper command writes runtime configuration;
- macOS, Linux, and Windows runner behavior.

The CI matrix targets Python 3.11 and the latest supported version on macOS, Linux, and Windows. Tests never invoke real provider APIs or touch the developer's home.

## Migration of the existing skill

The currently installed global `model-optimizer` is reference material, not an implementation dependency. Migration follows this order:

1. preserve its current text outside the new skill path;
2. run and record RED baselines without loading it;
3. design helper tests and watch them fail for missing behavior;
4. write the minimum new helper and skill content needed for GREEN;
5. compare the existing skill for useful criteria or edge cases not yet represented;
6. add an item only when a test or explicit product requirement justifies it;
7. verify the repository copy;
8. separately change installation/source-of-truth only after repository delivery is approved.

The repository skill must not reference an absolute path to the old installation. Name collisions are handled during deployment by removing or disabling the old source before enabling the repository copy; Pi's first-discovered-skill behavior is not treated as a safe migration mechanism.

## Distribution and integration boundary

The skill is published independently in `pablontiv/skills`. Consumers may copy the self-contained directory or install it through their supported Agent Skills mechanism.

The Pi Superpowers routing extension does not bundle, auto-load, or invoke this skill. Its maintenance documentation may say to run `model-optimizer`, produce a before/after plus PASS/FAIL/HANG report, obtain approval, and then update its versioned static profiles. The routing runtime retains deterministic mappings, no automatic fallback, and no dynamic switching.

## Acceptance criteria

1. Pi and OpenCode inventories contain exact locally advertised IDs and current assignments.
2. Provider readiness is captured without credential material.
3. Live checks classify PASS, FAIL, and HANG with bounded elapsed time and reason codes.
4. A live check artifact is digest-bound to its inventory.
5. Partial discovery cannot silently omit a failed source.
6. The helper cannot write runtime configuration or execute arbitrary shell fragments.
7. Online-only models never enter an assignable candidate set.
8. Broken current assignments appear as required remaps.
9. Adversarial validation compares model families rather than providers.
10. Unsupported effort appears only as prompt-level intent.
11. Before/after state and explicit approval precede every apply.
12. Reload semantics and post-reload agent-path checks are reported.
13. Cache, vision, cost, quotas, and limits retain provenance and uncertainty labels.
14. RED baselines fail for the intended reasons before `SKILL.md` is written.
15. The same scenarios pass with the skill loaded.
16. Helper unit tests pass without network or real-home access on macOS, Linux, and Windows.
17. The repository copy is self-contained and contains no personal paths.
18. The Superpowers routing extension remains independent of the optimizer at runtime.
