# Model Optimizer optimization flow

This reference expands the concise `SKILL.md` workflow. It is normative for `/skill:model-optimizer` responses but does not create any pre-approval mutation command.

## Trigger shape

- Trigger A: a new API key, subscription, provider, or model becomes usable. Reevaluate only routes materially affected by that newly usable capability plus unhealthy incumbents.
- Trigger B: a new or changed agent appears. Derive a normalized agent contract and select a route for that agent only, plus any directly affected adversarial pair.
- Never run a full runtime model × agent matrix sweep by default.

## Ordered flow

1. Detect Pi or OpenCode and ask only if ambiguous.
2. Inventory and delta: discover runtime version, ready providers, exact catalog-local models, current assignments, unassigned agents, source scopes, and semantic fingerprints. Ignore timestamp churn.
3. Read affected agent definitions using runtime scope precedence. Preserve effective tools, permissions, mutation authority, inheritance, source scope, and exact internal apply target.
4. Derive requirements and priority order from the definition, not model prestige.
5. Gate and shortlist. A route must be exact runtime-local, provider-ready, live at the proposed effort/variant, compatible with context/output/modalities/options, safe for required tools, and role-appropriate. Keep at most four routes including the incumbent.
6. Reconcile only bounded benchmark sources relevant to the affected role. Treat benchmarks as priors and keep identity uncertainty explicit.
7. Evaluate finalists with runtime-exact, tool-confined role evaluation: same runtime, provider/model, effort, agent system prompt, confined fixture tools, and versioned fixture.
8. Select gate-first. A challenger replaces a healthy incumbent only with a higher quality/contract tier, at least `0.10` role-score lift on each of two compatible fixtures, or at least `20%` operational gain on two comparable observations without reliability or intervention regression.
9. Return exactly one decision: `CHANGE`, `NO_CHANGE`, `NEEDS_MORE_EVIDENCE`, or `ABSTAIN`. Ties retain the incumbent.
10. Stop for explicit approval. After approval, use a private payload with exact target and source digest, back up, edit minimally, validate, reload, verify affected agent paths, and roll back with a second reload/path verification on failure.

## Archetypes and fallback guidance

- mechanical: bounded implementation with deterministic tests; bundled fixtures may be used when relevant.
- integration: multi-file coordination, API boundaries, or adapter behavior; require fixture coverage for integration contracts.
- debugger: root-cause or regression triage; bundled read-only regression fixtures may be used when relevant.
- architecture: design, trade-off, and cross-boundary reasoning; require an objective review rubric or representative task.
- reviewer: adversarial code/design review; enforce family independence when paired with a worker role.
- router/delegator: planning and task assignment; evaluate route selection accuracy and abstention behavior.
- researcher: evidence gathering and synthesis; require source-quality and uncertainty criteria.
- scout: broad discovery with concise relevance filtering; evaluate recall/precision against bounded sources.
- context-builder: summarization and context assembly; evaluate fidelity, privacy, and omission handling.

Use bundled fixtures only when the fixture matches the role requirements. For an unmatched agent or an agent without an objective success criterion, ask the user for one representative task and abstain until supplied. If the user supplies a task, create a bounded, versioned temporary fixture under the optimizer evaluation workspace; do not trust arbitrary project paths or commands as fixtures.

## Proposal rendering

The public proposal is concise and safe. Route effort must be visible when relevant; internal config targets, source paths, cache keys, output files, and artifact plumbing stay out of the rendered proposal.

```proposal
agent: implementer
current_model: openai/gpt-5.4-mini
current_effort: high
recommended_model: openai/gpt-5.4-mini
recommended_effort: high
reason: incumbent passed both mechanical fixtures and challengers did not show material lift
uncertainty_or_exclusion: opaque alias kept as FAMILY_PROXY until runtime-exact evidence exists
operational_trade_off: no added latency or cost; avoids routing churn
```

The internal approval payload is not shown as the public recommendation. It exists only after explicit approval is bound to the rendered proposal.

```approval-payload
{
  "agent": "implementer",
  "decision": "NO_CHANGE",
  "exact_apply_target": {
    "runtime": "opencode",
    "scope": "project",
    "container": "opencode.json",
    "agent_key": "implementer"
  },
  "source_digest": "sha256:discovered-source-bytes"
}
```

## Apply and rollback rules

- The evidence helper remains read-only.
- Before approval, emit only inventory, check, evaluate, and cache-benchmark evidence commands.
- The internal payload is `ApprovedChange(agent, previous_route, selected_route, apply_target, source_digest)`. Construct it only after explicit approval is bound to the concise proposal; do not derive write targets from the rendered proposal text.
- After approval, mutate only the native runtime source discovered during inventory. project-local Pi definitions map to project `.pi/subagents.json`; global Pi definitions map to `$PI_CODING_AGENT_DIR/subagents.json` or `~/.pi/agent/subagents.json`. project OpenCode config overrides global fields only where present. Do not copy inherited global values into project config.
- backup bytes must exactly equal the original source bytes. Place the timestamped backup beside the runtime-native configuration surface for the selected source scope.
- Validate syntax before reload.
- Verify the configured affected agent path after reload; a direct model probe is insufficient.
- If any write, validation, reload, or post-reload path check fails, restore with `os.replace` from the backup, validate the restored file, reload/restart again, and verify the restored agent path before reporting rollback success.
- Do not claim rollback success from restored bytes alone.

### Pi approved apply sequence

1. read selected config and fallback scope from the discovered Pi agent contract;
2. create timestamped backup in the runtime-native backup directory;
3. edit only `model_profiles[agent].model` and supported effort in the exact project or global `subagents.json`;
4. parse JSON to validate;
5. reload or restart/new session as required by the active Pi runtime;
6. invoke affected subagent path and verify it resolves to the selected route;
7. on failure, atomically restore from backup;
8. parse again to validate restored JSON;
9. perform the second reload/restart;
10. verify the restored agent path before reporting rollback success.

Do not copy inherited global values into project config.

### OpenCode approved apply sequence

1. read selected config and fallback scope from the discovered OpenCode agent contract;
2. create timestamped backup in the runtime-native backup directory;
3. edit only `agent.<name>.model` and `variant` in the exact discovered `opencode.json` source, or the Markdown frontmatter `model` and `variant` fields in the exact discovered Markdown definition;
4. parse JSON to validate JSON sources, or validate bounded Markdown frontmatter for Markdown sources;
5. reload or restart/new session as required by the active OpenCode runtime;
6. invoke affected agent path and verify it resolves to the selected route;
7. on failure, atomically restore from backup;
8. parse again to validate restored JSON or restored Markdown frontmatter;
9. perform the second reload/restart;
10. verify the restored agent path before reporting rollback success.

## Privacy and sandbox rules

The workflow must not persist or render secrets, API keys, credentials, raw prompts, raw responses, unrestricted tool arguments, source code, transcripts, exact config paths, cache keys, or paths under Pi/OpenCode configuration trees. Mutation/code-execution fixtures require an attested supported sandbox backend with scrubbed environment and network denial; if none exists, return `ABSTAIN` for that fixture rather than approximating safety.
