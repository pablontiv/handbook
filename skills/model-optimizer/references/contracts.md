# Model Optimizer helper contracts

`model-optimizer` evidence artifacts are UTF-8 JSON written by the read-only helper. Paths below are fictional examples; `/workspace/project` represents a user project directory.

The helper never authorizes configuration mutation.

## Inventory artifact

Schema: `model-optimizer.inventory/v1`.

```json
{
  "schema": "model-optimizer.inventory/v1",
  "created_at": "2026-08-19T00:00:00Z",
  "runtime": {
    "kind": "opencode",
    "version": "opencode 1.2.3",
    "cwd": "/workspace/project"
  },
  "sources": [
    "missing:global:opencode.json",
    "project:opencode.json"
  ],
  "current_assignments": [
    {
      "agent": "implementer",
      "model": "openai/gpt-5.6-terra",
      "options": {
        "variant": "high"
      },
      "source": "project:opencode.json"
    }
  ],
  "catalog_local": [
    {
      "exact_id": "openai/gpt-5.6-terra",
      "provider": "openai",
      "model": "gpt-5.6-terra",
      "family": "gpt-5",
      "context_window": 1050000,
      "max_output": 128000,
      "reasoning": true,
      "input_modes": [
        "text",
        "image"
      ],
      "tool_call": true,
      "cache_read": 0.2,
      "cache_write": 0.8,
      "input_cost": 1.25,
      "output_cost": 10.0,
      "variants": [
        "high",
        "low"
      ],
      "provenance": [
        "opencode models --verbose"
      ]
    }
  ],
  "provider_readiness": [
    {
      "provider": "openai",
      "status": "ready",
      "auth_type": "api",
      "reason_code": "auth_ready"
    }
  ],
  "exclusions": [],
  "warnings": [],
  "digest": "sha256:c72bef54a4f491effc6719d3b5c4209fc0e4a0c00dd16db9bafe57fa88942020"
}
```

Required to load: `schema`, `created_at`, `runtime.kind`, `runtime.version`, `runtime.cwd`, and `digest`. Helper output also serializes `sources`, `current_assignments`, `catalog_local`, `provider_readiness`, `exclusions`, and `warnings`; the current loader treats missing collection fields as empty. Nested required fields are the constructor-required fields in `helper.models`: assignments need `agent`, `model`, and `source`; model records need `exact_id`, `provider`, and `model`; provider readiness needs `provider`, `status`, and `reason_code`; exclusions need `subject` and `reason_code`. Optional metadata fields may be omitted by loaders or serialized as `null`: `family`, `context_window`, `max_output`, `reasoning`, `tool_call`, `cache_read`, `cache_write`, `input_cost`, `output_cost`, and `auth_type`. Empty arrays mean no evidence/items; `null` means the field exists but the helper did not know the value.

Digest rule: compute canonical JSON with sorted keys, compact separators, UTF-8, `ensure_ascii=false`, and strict finite JSON numbers after setting the inventory `digest` field to the empty string. Non-finite artifact numbers are rejected with `artifact_invalid_number`. The stored value is `sha256:` plus the SHA-256 hex digest. Health, evaluation, and cache evidence must bind to this exact digest. These files are internal helper mechanisms for current-run orchestration and optimizer state; users do not prepare them by hand.

## Health artifact

Schema: `model-optimizer.health/v1`.

```json
{
  "schema": "model-optimizer.health/v1",
  "created_at": "2026-08-19T00:01:00Z",
  "inventory_digest": "sha256:c72bef54a4f491effc6719d3b5c4209fc0e4a0c00dd16db9bafe57fa88942020",
  "checks": [
    {
      "model": "openai/gpt-5.6-terra",
      "effort": "high",
      "status": "PASS",
      "elapsed_ms": 423,
      "reason_code": "live_sentinel_matched",
      "response_matched": true,
      "detail": "PONG"
    }
  ]
}
```

Required to load: `schema`, `created_at`, and `inventory_digest`. `checks` is serialized by helper output and currently defaults to empty if absent. Each check requires `model`, `status`, `elapsed_ms`, `reason_code`, `response_matched`, and `detail`; `effort` is optional and serializes as `null` when no runtime-supported effort/variant was requested.

OpenCode live checks are fail-closed at a local safety boundary: before any `opencode run`, the adapter injects a per-check unique probe agent (`model-optimizer-probe-<token_hex_32>`), runs `opencode debug config`, and requires effective deny-all permission with no retained executable behavior. Any probe command failure, timeout, truncation, malformed JSON, missing probe agent, or permission conflict returns `live_unsafe_permission_config`, sets `response_matched` to `false`, and skips model launch.

## Evaluation artifact

Schema: `model-optimizer.evaluation/v1`.

The optional evaluation artifact is written only when `evaluate --output` is supplied. It is a bounded current-run summary for helper orchestration, not a user-prepared evidence document and not the persistent evidence store. The single optimizer state file remains the persistent cache.

```json
{
  "schema": "model-optimizer.evaluation/v1",
  "created_at": "2026-08-20T00:02:00Z",
  "inventory_digest": "sha256:c72bef54a4f491effc6719d3b5c4209fc0e4a0c00dd16db9bafe57fa88942020",
  "route": {
    "runtime_kind": "opencode",
    "runtime_version": "opencode 1.2.3",
    "model": "openai/gpt-5.6-terra",
    "effort": "high"
  },
  "agent_digest": "sha256:agent-definition",
  "fixture_id": "mechanical-slugify",
  "fixture_version": "1",
  "result": {
    "success": true,
    "role_score": 1.0,
    "contract_success": true,
    "elapsed_ms": 423,
    "metered_cost": null,
    "reason_codes": ["eval_pass"]
  }
}
```

The artifact may contain only schema/time, inventory digest, complete `RouteKey`, agent digest, fixture identity/version, and bounded summary fields. It must not serialize role prompts, task prompts, final model text, tool arguments, source code, secrets, credentials, raw transcripts, or configuration paths.

## Benchmark cache

`cache-benchmark` persists one normalized `BenchmarkSummary` through the locked state read-modify-write path under the resolved cache directory (`$XDG_CACHE_HOME/model-optimizer/state.json` or `$HOME/.cache/model-optimizer/state.json`). Cache writes are forbidden when that resolved state path overlaps Pi or OpenCode configuration trees. Runtime configuration remains read-only.

Benchmark observations require HTTPS source URLs, RFC3339 timestamps with timezone, finite metrics or the literal `omit`, complete runtime/model/effort route overlap with the current inventory, a ready provider, and an identity class from `EXACT`, `MODEL_EQUIVALENT`, `FAMILY_PROXY`, `ABSENT`, `UNKNOWN`, or `SOURCE_UNAVAILABLE`. `SOURCE_UNAVAILABLE` is preserved as unavailable-source evidence and is not rewritten to `ABSENT`; `FAMILY_PROXY` remains distinct from exact or model-equivalent evidence. Benchmark summaries expire at seven days, with entries exactly seven days old considered stale.

## Reason-code families

- `runtime_*`: missing, ambiguous, or unavailable runtime/executable/version detection.
- `inventory_*`: list, parse, source shape, current-assignment, metadata, or partial-discovery findings.
- `auth_*`: ready, not-ready, missing, expired, unknown, timeout, failed, or unlisted credential readiness.
- `live_*`: sentinel matched/missing, empty output, nonzero exit, timeout, unsupported model/variant, malformed events, or runtime error.
- `eval_*`: runtime-exact role evaluation binding, fixture, sandbox/isolation, adapter, audit, grader, timeout, or inconclusive infrastructure findings.
- `state_*`: cache path, lock, read, parse, permission, size, write, or atomic update findings.
- `identity_*`: invalid or unsupported benchmark identity class findings.
- `benchmark_*`: benchmark source, timestamp, metric, model/provider readiness, effort/variant, metadata, or cache normalization findings.
- `artifact_*`: schema, JSON, encoding, digest, shape, invalid non-finite numbers, serialization, or option validation.
- `usage_*`: invalid CLI arguments, timeout, duplicate arguments, or forbidden output paths.
- `redaction_*`: reserved for diagnostics that cannot be proven safe to persist.
- `provider_not_ready`: exclusion family for catalog-local models whose provider is not ready.

## Exit codes

- `0`: command completed and wrote complete successful evidence.
- `2`: usage, schema, artifact, invalid timeout/output path, or live precondition error.
- `3`: runtime detection or required runtime executable failure.
- `4`: inventory completed with explicit warnings/partial discovery, including `inventory_list_models_truncated` when structured catalog stdout was truncated after parsing available rows.
- `5`: health check completed and at least one candidate was `FAIL` or `HANG`; or evaluation completed with a conclusive model/contract failure.
- `6`: evaluation infrastructure, adapter, sandbox, or grader was inconclusive. This does not penalize the model and does not persist evaluation evidence.

## Provenance and uncertainty labels

Runtime-local provenance labels currently include `pi --list-models`, `models-store.json`, `models.json`, and `opencode models --verbose`. Cache fields (`cache_read`, `cache_write`), cost fields (`input_cost`, `output_cost`), vision capability (`input_modes` containing `image`), reasoning/tool flags, variants, and limits are metadata until a live check proves response health. Report cache as capability/pricing metadata unless runtime usage proves a cache hit. Quota and rate-limit evidence belongs in the reasoning/report or online-enrichment metadata, not in an invented inventory or health schema field.

Online documentation, advisors, and market catalogs may enrich overlapping live-local candidates only. They never create assignable candidates and never override exact runtime-local IDs.

## Migration from an existing copy

1. Locate every discovered `model-optimizer` source.
2. Compare content and back up user-owned modifications.
3. Install or copy the repository version of `skills/model-optimizer/`.
4. Disable or remove the old discovery source only after explicit approval.
5. Reload the harness.
6. Verify exactly one discovered skill and run a trivial `/skill:model-optimizer` invocation.

No global-copy migration action is authorized by this document; migration is documentation only and requires separate approval.
