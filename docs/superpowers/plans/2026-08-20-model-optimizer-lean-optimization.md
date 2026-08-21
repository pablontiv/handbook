# Model Optimizer Lean Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `model-optimizer` so a user can rerun the skill after adding models/providers or agents and receive a locally validated, approval-gated model mapping.

**Architecture:** Keep the skill as the user-facing orchestrator and keep helper commands read-only with respect to runtime configuration. Add focused units for normalized agent discovery and route policy, one seven-day summary cache, and runtime-exact/tool-confined role evaluation for Pi/OpenCode. Public benchmark reconciliation remains a skill-driven web-research step; only normalized summaries enter the cache.

**Tech Stack:** Python 3.11+ standard library, `unittest`, existing Pi/OpenCode CLIs, Markdown skill instructions, JSON fixtures.

**Spec:** `docs/superpowers/specs/2026-08-20-model-optimizer-lean-optimization-design.md`

## Global Constraints

- Target skill root: `/Users/pones/.agents/skills/model-optimizer`.
- Do not mutate Pi or OpenCode configuration from the evidence helper.
- Do not introduce third-party Python dependencies; parse only the bounded frontmatter fields the optimizer needs.
- Live health is never served from cache.
- Cached benchmark/evaluation summaries expire after seven days.
- Shortlists contain at most four routes, including a healthy incumbent.
- Every final route must preserve runtime/model/effort identity, pass an exact runtime-local live check, and pass at least one tool-confined role evaluation.
- `FAMILY_PROXY`, `ABSENT`, `UNKNOWN`, and `SOURCE_UNAVAILABLE` require stronger local evaluation and never receive exact benchmark credit.
- Candidate models never receive unrestricted host shell, ambient extensions/configuration, credentials, or arbitrary host paths during role evaluation.
- Essential custom tools are capability-probed separately; unsupported safe probes produce `ABSTAIN`.
- Configuration writes remain behind explicit approval and must include backup, validation, reload, agent-path verification, and rollback instructions.
- The skill directory is not currently a Git repository. Do not initialize Git without user approval; use verified task checkpoints instead of commit steps.
- Support both approved flows explicitly: optimize existing agents after a provider/model change, and select a route for a newly created agent.

## File Structure

**Create:**

- `helper/optimizer.py` — agent contracts, identity labels, hard gates, shortlist, stability selection.
- `helper/state.py` — minimal cache schemas, inventory delta, freshness, atomic persistence.
- `helper/evaluator.py` — trusted workspace, confined role-eval request/result/audit models, runtime event parsing, grading entry point.
- `evals/pi-confined-tools.ts` — Pi-only extension that overrides requested built-ins with fixture-confined operations and an allowlisted test runner.
- `evals/mechanical-slugify/eval.json` and project files — validated mechanical fixture.
- `evals/regression-timeout/eval.json` and project files — validated read-only debugging fixture.
- `references/optimization-flow.md` — concise orchestration, archetype, selection, apply, and rollback rules.
- `references/benchmark-sources.md` — bounded source registry and identity-matching rules.
- `tests/test_optimizer.py` — policy and agent-contract tests.
- `tests/test_state.py` — cache/delta tests.
- `tests/test_evaluator.py` — isolation, event parsing, grader, and fixture tests.

**Modify:**

- `helper/artifacts.py` — expose strict atomic JSON writing for state reuse.
- `helper/adapters/pi.py` — correct Pi scope discovery and build/run tool-confined role-eval commands.
- `helper/adapters/opencode.py` — discover assigned/unassigned agents and build/verify/run temporary confined OpenCode evaluation agents.
- `scripts/model_optimizer.py` — add `evaluate` and `cache-benchmark` read-only commands.
- `SKILL.md` — replace the manual selection narrative with the approved lean `optimize` flow.
- `references/contracts.md` — document internal evaluation/cache inputs, exit behavior, and non-mutation boundary.
- `tests/test_artifacts.py`, `tests/test_cli.py`, `tests/test_pi.py`, `tests/test_opencode.py`, `tests/test_skill_contract.py` — regression coverage.
- `tests/pressure/scenarios.json`, `tests/pressure/green.md` — approval, stale evidence, alias, and no-op pressure cases.

---

### Task 1: Add Pure Agent and Selection Policy

**Files:**
- Create: `helper/optimizer.py`
- Create: `tests/test_optimizer.py`
- Modify: `helper/adapters/pi.py`
- Modify: `helper/adapters/opencode.py`
- Modify: `tests/test_pi.py`
- Modify: `tests/test_opencode.py`

**Interfaces:**
- Consumes: existing `Inventory`, `ModelRecord`, `HealthCheck`, and `CurrentAssignment` from `helper.models`.
- Produces:
  - `parse_agent_definition(path: Path, *, scope: str, config_path: Path) -> AgentContract`
  - `discover_agent_contracts(runtime: RuntimeKind, home: Path, cwd: Path, environ: Mapping[str, str]) -> tuple[AgentContract, ...]`
  - `classify_identity(runtime_route: RouteKey, observation: BenchmarkObservation | None, source_available: bool) -> IdentityMatch`
  - `gate_candidate(requirements: RoleRequirements, route: RouteKey, model: ModelRecord, health: HealthCheck) -> tuple[str, ...]`
  - `shortlist_candidates(requirements: RoleRequirements, candidates: Sequence[CandidateEvidence], incumbent: RouteKey | None, limit: int = 4) -> tuple[CandidateEvidence, ...]`
  - `choose_mapping(requirements: RoleRequirements, candidates: Sequence[CandidateEvidence], incumbent: RouteKey | None) -> MappingDecision`

- [ ] **Step 1: Write failing tests for bounded agent frontmatter parsing**

```python
# tests/test_optimizer.py
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from helper.optimizer import parse_agent_definition


class AgentContractTests(unittest.TestCase):
    def test_parses_inline_and_sequence_tool_allowlists_without_yaml_dependency(self):
        samples = (
            "---\nname: mechanical\ndescription: Small edits\ntools: read, edit, bash\n---\nBody\n",
            "---\nname: mechanical\ndescription: Small edits\ntools:\n  - read\n  - edit\n  - bash\n---\nBody\n",
        )
        for text in samples:
            with self.subTest(text=text), TemporaryDirectory() as td:
                path = Path(td) / "agent.md"
                path.write_text(text, encoding="utf-8")
                contract = parse_agent_definition(
                    path,
                    scope="global",
                    config_path=Path(td) / "subagents.json",
                )
                self.assertEqual(contract.name, "mechanical")
                self.assertEqual(contract.tools, ("read", "edit", "bash"))
                self.assertEqual(contract.body, "Body")
                self.assertTrue(contract.digest.startswith("sha256:"))
```

Add tests that reject missing delimiters, duplicate/unsafe tool names, nested frontmatter, non-UTF-8 content, and bodies larger than the documented bound with stable `agent_definition_*` errors.

- [ ] **Step 2: Run the parser tests and confirm RED**

Run:

```bash
cd /Users/pones/.agents/skills/model-optimizer
python3 -m unittest tests.test_optimizer.AgentContractTests -v
```

Expected: import failure because `helper.optimizer` does not exist.

- [ ] **Step 3: Implement immutable policy types and bounded parser**

```python
# helper/optimizer.py
class IdentityMatch(StrEnum):
    EXACT = "EXACT"
    MODEL_EQUIVALENT = "MODEL_EQUIVALENT"
    FAMILY_PROXY = "FAMILY_PROXY"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


@dataclass(frozen=True)
class RouteKey:
    runtime_kind: RuntimeKind
    runtime_version: str
    model: str
    effort: str | None


@dataclass(frozen=True)
class PermissionRule:
    capability: str
    pattern: str
    action: str  # allow | ask | deny


@dataclass(frozen=True)
class AgentContract:
    name: str
    description: str
    mode: str | None
    model: str | None
    effort: str | None
    tools: tuple[str, ...]  # normalized effective tool names
    permissions: tuple[PermissionRule, ...]
    mutation_authority: str  # denied | confined | unrestricted | unknown
    body: str
    scope: str
    definition_source: str
    assignment_source: str | None
    inheritance_sources: tuple[str, ...]
    apply_target: str | None
    digest: str


@dataclass(frozen=True)
class RoleRequirements:
    archetype: str
    required_tools: tuple[str, ...]
    essential_custom_tools: tuple[str, ...]
    requires_vision: bool
    requires_mutation: bool
    min_context: int | None
    min_output: int | None
    allowed_efforts: tuple[str, ...]
    structured_output: bool
    adversarial_against_family: str | None
    priority_order: tuple[str, ...]


@dataclass(frozen=True)
class RunObservation:
    run_id: str
    elapsed_ms: int
    reliable: bool
    intervention_count: int
    metered_cost: float | None


@dataclass(frozen=True)
class FixtureEvidence:
    fixture_id: str
    fixture_version: str
    success: bool
    role_score: float
    contract_success: bool
    runs: tuple[RunObservation, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CandidateEvidence:
    route: RouteKey
    model: ModelRecord
    health: HealthCheck
    identity: IdentityMatch
    fixtures: tuple[FixtureEvidence, ...]
    benchmark_score: float | None
    reliability_rate: float | None
    median_elapsed_ms: int | None
    metered_cost: float | None
    incumbent: bool = False


@dataclass(frozen=True)
class MappingDecision:
    status: str  # CHANGE | NO_CHANGE | NEEDS_MORE_EVIDENCE | ABSTAIN
    selected_route: RouteKey | None
    next_fixture: str | None
    reasons: tuple[str, ...]
```

Implement a bounded Markdown frontmatter parser for the documented agent subset: `name`, `description`, `mode`, `model`, `variant`, scalar/list/map `tools`, and nested permission pattern maps. Normalize JSON and Markdown definitions into ordered `PermissionRule` values after applying scope precedence. Reject YAML tags, aliases, anchors, duplicate keys, unknown permission actions, unsupported nesting, and ambiguous inheritance instead of pretending to parse general YAML.

- [ ] **Step 4: Write failing gate, shortlist, and stability tests**

Tests must prove:

```python
self.assertEqual(gate_candidate(vision_role, text_route, text_only_model, passing_health), ("required_vision_missing",))
self.assertEqual(len(shortlist_candidates(role, candidates, incumbent=current_route, limit=4)), 4)
self.assertIn(current_route, [item.route for item in shortlist])
self.assertEqual(choose_mapping(role, one_fixture_tie, current_route).status, "NEEDS_MORE_EVIDENCE")
self.assertEqual(choose_mapping(role, unresolved_two_fixture_tie, current_route).status, "NO_CHANGE")
self.assertEqual(choose_mapping(role, no_eligible_candidates, None).status, "ABSTAIN")
```

Also verify unavailable/live-failing routes never enter a shortlist, effort survives through selection, context/output/vision/family gates are enforced, and identity classification covers exact/equivalent/proxy/absent/unknown/source-unavailable. A one-fixture quality tie must return `NEEDS_MORE_EVIDENCE`, not immediately retain or replace.

- [ ] **Step 5: Implement runtime-specific agent discovery**

Pi discovery and the existing inventory snapshot must share one config-root resolver: honor `PI_CODING_AGENT_DIR` (fallback `~/.pi/agent`), global `agents/` and `subagents/`, project `.pi/agents/` and `.pi/subagents/`, project definitions overriding global, and project `.pi/subagents.json` rather than the current erroneous `.pi/agent/subagents.json`. OpenCode discovery must honor `XDG_CONFIG_HOME`/`~/.config/opencode`, `.opencode/agents/`, and normalize both global/project Markdown agents and inline global/project `opencode.json` agents, including definitions with no model field. Tests must cover structured Markdown tools/permissions, inline JSON permissions, inherited fields, same-name scope collisions, assigned and unassigned definitions, mode, mutation authority, exact definition/assignment/inheritance sources, exact apply target, and current assignment discovery through the same source paths.

- [ ] **Step 6: Implement gate-first adaptive selection**

Use lexicographic comparison: objective role score and contract compliance first, then fields named in `priority_order`. Never average unrelated dimensions into one universal score. A challenger has material advantage only with a higher mandatory tier, a `>=0.10` role-score gain on each of two compatible fixtures, or a `>=20%` gain in the highest-priority operational metric across at least two comparable `RunObservation` values with no reliability/intervention regression. Tests must fail if aggregates claim an advantage unsupported by their per-fixture runs. Preserve the incumbent on unresolved ties.

- [ ] **Step 7: Run Task 1 tests and the existing suite**

```bash
python3 -m unittest tests.test_optimizer -v
python3 -m unittest discover -s tests -v
```

Expected: all tests pass; the existing 147-test baseline has no regressions.

- [ ] **Step 8: Record a verified checkpoint**

Record changed files and exact passing test counts in the execution log. Do not commit because the target directory has no Git repository.

---

### Task 2: Add the Lightweight Seven-Day State Cache

**Files:**
- Create: `helper/state.py`
- Create: `tests/test_state.py`
- Modify: `helper/artifacts.py`
- Modify: `tests/test_artifacts.py`

**Interfaces:**
- Consumes: strict JSON/digest helpers, normalized inventory components, and discovered agent contracts.
- Produces:
  - `state_path(environ: Mapping[str, str], home: Path, config_trees: Sequence[Path]) -> Path`
  - `semantic_snapshot(inventory: Inventory, agents: Sequence[AgentContract]) -> SemanticSnapshot`
  - `load_state(path: Path) -> OptimizerState`
  - `update_state(path: Path, transform: Callable[[OptimizerState], OptimizerState]) -> OptimizerState`
  - `inventory_delta(previous: SemanticSnapshot | None, current: SemanticSnapshot) -> InventoryDelta`
  - `fresh_evaluation(state: OptimizerState, key: EvaluationKey, now: datetime) -> EvaluationSummary | None`
  - `fresh_benchmark(state: OptimizerState, key: BenchmarkKey, now: datetime) -> BenchmarkSummary | None`

- [ ] **Step 1: Write failing cache-path, freshness, and privacy tests**

```python
class StateTests(unittest.TestCase):
    def test_state_path_uses_xdg_cache_home_then_home_fallback(self):
        self.assertEqual(
            state_path({"XDG_CACHE_HOME": "/cache"}, Path("/home/u"), (Path("/home/u/.pi/agent"),)),
            Path("/cache/model-optimizer/state.json"),
        )
        self.assertEqual(
            state_path({}, Path("/home/u"), (Path("/home/u/.pi/agent"),)),
            Path("/home/u/.cache/model-optimizer/state.json"),
        )

    def test_summary_expires_at_seven_days_and_key_changes_invalidate(self):
        self.assertIsNotNone(fresh_evaluation(state, key, created + timedelta(days=6, seconds=86399)))
        self.assertIsNone(fresh_evaluation(state, key, created + timedelta(days=7)))
        high_effort_key = replace(key, route=replace(key.route, effort="high"))
        self.assertIsNone(fresh_evaluation(state, high_effort_key, created))
        self.assertIsNone(fresh_benchmark(state, benchmark_key, created + timedelta(days=7)))
```

Assert `XDG_CACHE_HOME` must be absolute and the resolved cache path cannot be inside any Pi/OpenCode configuration tree. Serialized state contains no prompt text, response text, tool arguments, source code, authorization values, API keys, or credentials. Corrupt JSON must return an empty state with a stable warning rather than abort optimization.

- [ ] **Step 2: Run Task 2 tests and confirm RED**

```bash
python3 -m unittest tests.test_state -v
```

Expected: import failure because `helper.state` does not exist.

- [ ] **Step 3: Expose strict atomic JSON writing**

Add to `helper/artifacts.py`:

```python
def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, _json_dumps_strict(value, sort_keys=True, indent=2) + "\n")
```

Add tests for parent creation, strict finite numbers, hardlink replacement, concurrent writes, and no temporary-file debris.

- [ ] **Step 4: Implement state schemas and keying**

```python
@dataclass(frozen=True)
class SemanticSnapshot:
    runtime_fingerprint: str
    model_fingerprints: Mapping[str, str]
    readiness_fingerprints: Mapping[str, str]
    assignment_fingerprints: Mapping[str, str]
    agent_fingerprints: Mapping[str, str]


@dataclass(frozen=True)
class EvaluationKey:
    route: RouteKey
    agent_digest: str
    tool_digest: str
    fixture_id: str
    fixture_version: str
    model_fingerprint: str


@dataclass(frozen=True)
class EvaluationSummary:
    key: EvaluationKey
    created_at: str
    success: bool
    role_score: float
    contract_success: bool
    elapsed_ms: int
    metered_cost: float | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkKey:
    route: RouteKey
    source_name: str
    benchmark: str
    benchmark_version: str
    evaluated_model_identity: str
    reasoning_mode: str | None


@dataclass(frozen=True)
class BenchmarkSummary:
    route: RouteKey
    identity: str
    source_name: str
    source_url: str
    benchmark: str
    benchmark_version: str
    harness_or_agent: str | None
    evaluated_model_identity: str
    reasoning_mode: str | None
    observed_at: str
    cached_at: str
    metric_name: str
    metric_value: float | None


@dataclass(frozen=True)
class OptimizerState:
    schema: str
    snapshot: SemanticSnapshot | None
    evaluations: tuple[EvaluationSummary, ...]
    benchmarks: tuple[BenchmarkSummary, ...]
    warnings: tuple[str, ...] = ()
```

Store summary metrics only. Semantic fingerprints exclude `created_at`, artifact digests, and ordering noise. Use canonical hashes for tool allowlists, routes, assignments, provider readiness, model metadata, and normalized agent sources.

- [ ] **Step 5: Implement and test delta detection**

Cover new/removed models, readiness transitions, new/changed/removed/unassigned agents, assignment changes, model metadata changes, missing incumbents, and the no-change case. Prove two inventories that differ only in `created_at` produce the same semantic snapshot. A first run marks components as new without requesting a full Cartesian evaluation.

Implement state updates as one locked read-modify-write transaction, not merely an atomic final replacement. Test concurrent benchmark/evaluation writers, write failures, and seven-day freshness for both summary kinds.

- [ ] **Step 6: Run Task 2 and full tests**

```bash
python3 -m unittest tests.test_artifacts tests.test_state -v
python3 -m unittest discover -s tests -v
```

Expected: all pass.

- [ ] **Step 7: Record a verified checkpoint**

Record cache privacy assertions, corruption fallback, and passing test counts. Do not commit without a repository.

---

### Task 3: Implement Runtime-Exact, Tool-Confined Role Evaluation

**Files:**
- Create: `helper/evaluator.py`
- Create: `evals/pi-confined-tools.ts`
- Create: `tests/test_evaluator.py`
- Modify: `helper/adapters/pi.py`
- Modify: `helper/adapters/opencode.py`
- Modify: `tests/test_pi.py`
- Modify: `tests/test_opencode.py`

**Interfaces:**
- Consumes: validated `RouteKey`, `ModelRecord`, normalized `AgentContract`, trusted prepared workspace, fixture policy, and `CommandRunner`.
- Produces:
  - `PreparedWorkspace`
  - `RoleEvalRequest`
  - `ToolAudit`
  - `RoleEvalResult`
  - `PiAdapter.role_eval(request, context) -> RoleEvalResult`
  - `OpenCodeAdapter.role_eval(request, context) -> RoleEvalResult`
  - `parse_pi_eval_events(text: str, workspace: PreparedWorkspace) -> ParsedEvalOutput`
  - `parse_opencode_eval_events(text: str, workspace: PreparedWorkspace) -> ParsedEvalOutput`

- [ ] **Step 1: Write failing request and workspace validation tests**

```python
@dataclass(frozen=True)
class PreparedWorkspace:
    root: Path
    token: str
    sandbox_backend: str | None


@dataclass(frozen=True)
class CapabilityAttestation:
    tool_name: str
    probe_id: str
    status: str  # PASS | FAIL | INCONCLUSIVE
    observed_at: str
    probe_digest: str


@dataclass(frozen=True)
class AllowedCommand:
    command_id: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class FixturePolicy:
    fixture_id: str
    fixture_version: str
    manifest_digest: str
    grader_id: str
    allowed_read_paths: tuple[str, ...]
    allowed_write_paths: tuple[str, ...]
    allowed_commands: tuple[AllowedCommand, ...]
    requires_code_execution: bool
    capability_attestations: tuple[CapabilityAttestation, ...]


@dataclass(frozen=True)
class RoleEvalRequest:
    route: RouteKey
    model_record: ModelRecord
    agent: AgentContract
    requirements: RoleRequirements
    workspace: PreparedWorkspace
    fixture: FixturePolicy
    task: str
    timeout: float


@dataclass(frozen=True)
class CommandAudit:
    command_id: str
    exit_code: int | None
    elapsed_ms: int
    sandbox_backend: str


@dataclass(frozen=True)
class ToolAudit:
    tool_names: tuple[str, ...]
    command_runs: tuple[CommandAudit, ...]
    changed_paths: tuple[str, ...]
    outside_workspace_attempts: int
    unauthorized_tools: tuple[str, ...]


@dataclass(frozen=True)
class RoleEvalResult:
    route: RouteKey
    fixture_id: str
    fixture_version: str
    manifest_digest: str
    status: str  # PASS | FAIL | HANG | INCONCLUSIVE
    elapsed_ms: int
    final_text: str
    audit: ToolAudit
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    metered_cost: float | None
    reason_codes: tuple[str, ...]
```

Tests must reject a request when route/model IDs differ, effort is unsupported, requirements disagree with agent authority, fixture identity/digest/grader disagrees with the prepared marker, the workspace token is invalid, resolved policy paths escape the prepared root, task/body is empty, timeout is invalid, tools contain `subagent_*`, an allowed command lacks a stable command ID, or an essential custom tool lacks a fresh matching `CapabilityAttestation(PASS)`.

- [ ] **Step 2: Implement and test the Pi confined-tools extension**

`evals/pi-confined-tools.ts` must be the only loaded extension. Start Pi with `--no-extensions --no-builtin-tools -e <absolute-confined-extension>` plus `--no-session --no-context-files --no-skills --no-prompt-templates`. The extension reads a bounded policy file created by the helper and registers only the requested built-in names. File operations resolve real paths and reject anything outside the prepared workspace. The `bash` override accepts only exact manifest commands, runs with a scrubbed environment, disables session-environment exposure, and rejects shell operators or alternate cwd.

Assert command construction includes:

```python
for flag in ("--no-extensions", "--no-builtin-tools", "--extension", "--no-session", "--no-context-files", "--no-skills", "--no-prompt-templates", "--tools", "--system-prompt"):
    self.assertIn(flag, argv)
self.assertEqual(argv[argv.index("--model") + 1], request.route.model)
self.assertEqual(argv[argv.index("--thinking") + 1], request.route.effort)
self.assertEqual(argv[argv.index("--tools") + 1], ",".join(request.agent.tools))
```

If an agent requests a custom tool, do not load ambient extensions. Require a separate safe capability probe or return `eval_essential_custom_tool_unproven`.

- [ ] **Step 3: Add process-sandbox selection and fail-closed behavior**

Implement `select_sandbox_backend()` with supported adapters for macOS `sandbox-exec`, Linux `bwrap`, and Docker when available. Candidate-generated code executes only through the selected backend with network denied, a scrubbed environment, workspace-only writes, and read access limited to runtime libraries needed by the fixture. If a fixture requires code execution and no backend passes a self-test, return `INCONCLUSIVE` with `eval_sandbox_unavailable`; selection converts an essential inconclusive evaluation to `ABSTAIN`.

Tests must use fake executables/profiles and prove the candidate process cannot read a sentinel outside the workspace, cannot see a sentinel secret environment variable, and cannot open a network listener. Do not claim host isolation from `cwd` alone.

- [ ] **Step 4: Implement Pi event parsing and bounded audit facts**

Run with `stdout_limit=MAX_STDOUT_LIMIT_CHARS`. Parse JSONL tool events transiently, normalize relative/absolute paths against the prepared root, map exact allowed test commands to stable manifest command IDs, and record bounded `CommandAudit(command_id, exit_code, elapsed_ms, sandbox_backend)` values before discarding raw arguments. Derive test execution from successful required command IDs, never from a free-standing boolean. Malformed/truncated streams, manifest mismatch, or missing audit evidence are `INCONCLUSIVE`. Never persist `final_text` or tool arguments.

- [ ] **Step 5: Write failing OpenCode isolated-config tests**

Create a new temporary `XDG_CONFIG_HOME`; do not merge ambient `OPENCODE_CONFIG_CONTENT`. Preserve only the runtime authentication channel required for the provider. Generate a unique agent with deny-all defaults, `external_directory: "deny"`, file permissions limited to the fixture, and candidate `bash: "deny"`. The trusted evaluator, not the candidate agent, runs manifest test commands afterward through the selected process sandbox with a scrubbed environment. Do not use deprecated `tools` booleans.

```json
{
  "permission": {"*": "deny", "external_directory": "deny"},
  "agent": {
    "model-optimizer-eval-<32 hex>": {
      "description": "isolated model optimizer evaluation",
      "prompt": "<agent body>",
      "model": "provider/model",
      "variant": "high",
      "permission": {
        "*": "deny",
        "external_directory": "deny",
        "read": {"*": "deny", "<workspace>/**": "allow"},
        "edit": {"*": "deny", "<allowed-write>/**": "allow"},
        "bash": "deny"
      }
    }
  }
}
```

Require `opencode debug config --pure` under the temporary config root to match prompt/model/variant and exact permission rules before launch. Add hostile-global-config tests proving ambient instructions, plugins, tools, and permissions do not survive.

- [ ] **Step 6: Implement OpenCode execution and audit parsing**

Run `opencode run --pure --format json --model <route.model> --variant <route.effort> --agent <unique-agent> --dir <workspace> <task>`. Parse confined file-tool audit facts, then run manifest tests through the trusted sandbox backend and append their stable command IDs/results to `command_runs`. Preserve quota/rate-limit reason codes separately from model-quality failures. Any permission ask in non-interactive mode is inconclusive, not automatically approved.

- [ ] **Step 7: Test mutation and credential boundaries**

Prove both runtimes expose only confined tools, deny outside paths, prevent unrestricted shell, use the exact route effort, preserve runtime config bytes, redact diagnostics, reject unsupported custom tools, and terminate timed-out process groups. The evaluator must independently run `git diff --name-only` through its trusted runner to verify changed paths; it must not trust the model report.

- [ ] **Step 8: Run focused and full tests**

```bash
python3 -m unittest tests.test_evaluator tests.test_pi tests.test_opencode -v
python3 -m unittest discover -s tests -v
```

Expected: all pass.

- [ ] **Step 9: Record a verified checkpoint**

Record sandbox self-tests, exact Pi/OpenCode argv/effective-config assertions, audit facts, and test counts.

---

### Task 4: Add Trusted Pilot Fixtures and Semantic Graders

**Files:**
- Create: `evals/mechanical-slugify/eval.json`
- Create: `evals/mechanical-slugify/project/slugify.py`
- Create: `evals/mechanical-slugify/project/test_slugify.py`
- Create: `evals/mechanical-duration/eval.json`
- Create: `evals/mechanical-duration/project/duration.py`
- Create: `evals/mechanical-duration/project/test_duration.py`
- Create: `evals/regression-timeout/eval.json`
- Create: `evals/regression-timeout/project/settings.py`
- Create: `evals/regression-timeout/project/client.py`
- Create: `evals/regression-timeout/project/service.py`
- Create: `evals/regression-timeout/project/test_service.py`
- Create: `evals/regression-retry-delay/eval.json`
- Create: `evals/regression-retry-delay/project/settings.py`
- Create: `evals/regression-retry-delay/project/worker.py`
- Create: `evals/regression-retry-delay/project/test_worker.py`
- Modify: `helper/evaluator.py`
- Modify: `tests/test_evaluator.py`
- Create: `tests/replay_pilots.py`

**Interfaces:**
- Produces:
  - `load_fixture(skill_root: Path, fixture_id: str) -> EvalFixture`
  - `load_representative_fixture(temp_root: Path, fixture_path: Path, token: str) -> EvalFixture`
  - `prepare_fixture(fixture: EvalFixture) -> PreparedWorkspace`
  - `grade_fixture(fixture: EvalFixture, workspace: Path, result: RoleEvalResult) -> GradeResult`
  - `GradeResult(status: str, role_score: float, contract_success: bool, reason_codes: tuple[str, ...])`, where `role_score` is finite and bounded to `0.0..1.0`.
  - `tests/replay_pilots.py --runtime <pi|opencode> --case <mechanical|regression> --model <route> [--model <route> ...]`, which runs inventory/check and both compatible fixtures for the case, feeds per-run summaries into `choose_mapping`, and exits nonzero with fewer than two live candidates, fewer than two conclusive fixtures per finalist, or any infrastructure failure.

- [ ] **Step 1: Write failing trusted-fixture boundary tests**

Require fixture IDs to match `^[a-z0-9][a-z0-9-]{0,63}$`, resolve bundled fixtures beneath `<skill-root>/evals`, reject symlink/path escape, reject unknown grader IDs, and bound manifest/file sizes. A user-requested representative task may use a skill-generated temporary fixture only when its path is beneath the evaluator-owned temp root and its unpredictable marker token matches; it cannot reference user project paths, ambient commands, or unknown graders.

- [ ] **Step 2: Add the mechanical fixture exactly as validated**

`eval.json`:

```json
{
  "schema": "model-optimizer.eval-fixture/v1",
  "id": "mechanical-slugify",
  "version": "1",
  "archetype": "mechanical",
  "task": "Implement slugify.py to satisfy the existing tests. Read files first, modify only slugify.py, run the complete unittest suite, and do not commit.",
  "grader": "mechanical-slugify-v1",
  "allowed_changed_files": ["slugify.py"],
  "allowed_commands": [{"id": "python-unittest", "argv": ["python3", "-m", "unittest", "discover", "-v"]}],
  "requires_code_execution": true
}
```

`slugify.py`:

```python
def slugify(value: str) -> str:
    """Return a lowercase ASCII slug separated by single hyphens."""
    raise NotImplementedError
```

`test_slugify.py`:

```python
import unittest
from slugify import slugify


class SlugifyTests(unittest.TestCase):
    def test_words_and_whitespace(self):
        self.assertEqual(slugify("  Hello,   World!  "), "hello-world")

    def test_collapses_separators(self):
        self.assertEqual(slugify("one___two---three"), "one-two-three")

    def test_ascii_normalization(self):
        self.assertEqual(slugify("Crème Brûlée"), "creme-brulee")

    def test_empty_after_normalization(self):
        self.assertEqual(slugify("!!!"), "")

    def test_rejects_non_string(self):
        with self.assertRaises(TypeError):
            slugify(123)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Add a second compatible mechanical fixture**

`evals/mechanical-duration/eval.json`:

```json
{
  "schema": "model-optimizer.eval-fixture/v1",
  "id": "mechanical-duration",
  "version": "1",
  "archetype": "mechanical",
  "task": "Implement duration.py to satisfy the existing tests. Modify only duration.py and do not commit.",
  "grader": "mechanical-duration-v1",
  "allowed_changed_files": ["duration.py"],
  "allowed_commands": [{"id": "python-unittest", "argv": ["python3", "-m", "unittest", "discover", "-v"]}],
  "requires_code_execution": true
}
```

`duration.py`:

```python
def parse_duration(value: str) -> int:
    """Return the duration in seconds for tokens such as '1h 30m 5s'."""
    raise NotImplementedError
```

`test_duration.py`:

```python
import unittest
from duration import parse_duration


class DurationTests(unittest.TestCase):
    def test_combined_units(self):
        self.assertEqual(parse_duration("1h 30m 5s"), 5405)

    def test_single_unit(self):
        self.assertEqual(parse_duration("45m"), 2700)

    def test_whitespace_and_case(self):
        self.assertEqual(parse_duration(" 2H   3m "), 7380)

    def test_rejects_unknown_text(self):
        with self.assertRaises(ValueError):
            parse_duration("tomorrow")

    def test_rejects_non_string(self):
        with self.assertRaises(TypeError):
            parse_duration(None)
```

- [ ] **Step 4: Add the first regression-triage fixture exactly as validated**

`eval.json`:

```json
{
  "schema": "model-optimizer.eval-fixture/v1",
  "id": "regression-timeout",
  "version": "1",
  "archetype": "debugger",
  "task": "Diagnose the failing test suite. Do not modify any files.",
  "grader": "regression-timeout-v1",
  "allowed_changed_files": [],
  "allowed_commands": [{"id": "python-unittest", "argv": ["python3", "-m", "unittest", "discover", "-v"]}],
  "requires_code_execution": true
}
```

`settings.py`:

```python
DEFAULTS = {"timeout_ms": 5000, "retries": 3}
```

`client.py`:

```python
from settings import DEFAULTS


def request_options(overrides=None):
    """Build options for an HTTP client whose timeout parameter is in seconds."""
    config = {**DEFAULTS, **(overrides or {})}
    return {
        "timeout": config["timeout_ms"],
        "retries": config["retries"],
    }
```

`service.py`:

```python
from client import request_options


def startup_config():
    return request_options()
```

`test_service.py`:

```python
import unittest
from service import startup_config


class StartupConfigTests(unittest.TestCase):
    def test_default_timeout_is_five_seconds(self):
        self.assertEqual(startup_config()["timeout"], 5.0)

    def test_retry_count_is_preserved(self):
        self.assertEqual(startup_config()["retries"], 3)
```

The grader requires the millisecond/second mismatch, `client.py` line 8 evidence, `/1000` correction, fields `status`, `root_cause`, `evidence`, `proposed_fix`, and `confidence`, plus zero tracked modifications.

- [ ] **Step 5: Add a second compatible regression-triage fixture**

`evals/regression-retry-delay/eval.json`:

```json
{
  "schema": "model-optimizer.eval-fixture/v1",
  "id": "regression-retry-delay",
  "version": "1",
  "archetype": "debugger",
  "task": "Diagnose the failing retry-delay test. Do not modify any files.",
  "grader": "regression-retry-delay-v1",
  "allowed_changed_files": [],
  "allowed_commands": [{"id": "python-unittest", "argv": ["python3", "-m", "unittest", "discover", "-v"]}],
  "requires_code_execution": true
}
```

`settings.py`:

```python
RETRY_DELAY_MS = 250
```

`worker.py`:

```python
from time import sleep
from settings import RETRY_DELAY_MS


def wait_before_retry():
    sleep(RETRY_DELAY_MS)
```

`test_worker.py`:

```python
import unittest
from unittest.mock import patch
from worker import wait_before_retry


class RetryDelayTests(unittest.TestCase):
    @patch("worker.sleep")
    def test_delay_is_quarter_second(self, mocked_sleep):
        wait_before_retry()
        mocked_sleep.assert_called_once_with(0.25)
```

The grader requires the millisecond/second mismatch, `worker.py:6` evidence, `/1000` correction, all five structured diagnosis fields, and zero tracked modifications.

- [ ] **Step 6: Implement semantic grading**

Line evidence must accept single lines, ranges, and lists:

```python
def cited_lines(text: str, filename: str) -> set[int]:
    lines: set[int] = set()
    for spec in re.findall(rf"{re.escape(filename)}:([0-9,-]+)", text, re.IGNORECASE):
        for part in spec.split(","):
            if "-" in part:
                start, end = map(int, part.split("-", 1))
                lines.update(range(start, end + 1))
            else:
                lines.add(int(part))
    return lines
```

Do not treat stylistic formatting differences as failures. Do fail wrong technical cause, missing required fields, unauthorized changes, or absent test execution. Graders assign `role_score=1.0` only when every objective criterion passes; partial objective credit must be explicit per fixture and never inferred from prose length.

- [ ] **Step 7: Verify all four fixtures and material-advantage evidence**

Run each fixture's baseline tests before model execution and require the expected failing state. For mechanical green verification, replace the stub with this exact known-good solution and require 5/5 tests:

```python
import re
import unicodedata


def slugify(value: str) -> str:
    """Return a lowercase ASCII slug separated by single hyphens."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
```

For the second mechanical green verification, require 5/5 tests with:

```python
import re


def parse_duration(value: str) -> int:
    """Return the duration in seconds for tokens such as '1h 30m 5s'."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    if not re.fullmatch(r"\s*(?:\d+\s*[hms]\s*)+", value, re.IGNORECASE):
        raise ValueError("invalid duration")
    factors = {"h": 3600, "m": 60, "s": 1}
    return sum(int(number) * factors[unit.lower()] for number, unit in re.findall(r"(\d+)\s*([hms])", value, re.IGNORECASE))
```

For the first regression green verification, use this exact accepted diagnosis:

```text
status: diagnosed
root_cause: client.py returns timeout_ms without converting milliseconds to seconds
evidence: client.py:8 and test_service.py:7
proposed_fix: divide config["timeout_ms"] by 1000
confidence: high
```

For the second regression fixture, require:

```text
status: diagnosed
root_cause: worker.py passes RETRY_DELAY_MS directly to sleep, which expects seconds
evidence: worker.py:6 and settings.py:1
proposed_fix: divide RETRY_DELAY_MS by 1000 before calling sleep
confidence: high
```

Reject diagnoses blaming the caller, missing `/1000`, any regression-file mutation, or a mechanical run lacking the successful `python-unittest` command ID. Accept equivalent line/range/list evidence. Add selection tests in which a challenger wins by `>=0.10` on both mechanical fixtures, loses when only one fixture improves, wins by `>=20%` over two comparable runs, and loses on reliability/intervention regression despite faster aggregate latency.

- [ ] **Step 8: Run focused and full tests**

```bash
python3 -m unittest tests.test_evaluator -v
python3 tests/replay_pilots.py --fixtures-only
python3 -m unittest discover -s tests -v
```

Expected: all pass.

- [ ] **Step 9: Record a verified checkpoint**

Record four baseline-red cases, four known-solution/diagnosis-green cases, semantic line-format cases, two-fixture/two-run material-advantage cases, and full-suite count.

---

### Task 5: Add Read-Only CLI Commands for Evaluation and Benchmark Cache

**Files:**
- Modify: `scripts/model_optimizer.py`
- Modify: `helper/evaluator.py`
- Modify: `references/contracts.md`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_artifacts.py`

**Interfaces:**
- New command:

```text
model_optimizer.py evaluate \
  --inventory <inventory.json> \
  --agent <normalized-agent-name> \
  --model <provider/model> \
  --effort <level> \
  (--fixture <fixture-id> | --fixture-path <evaluator-temp-path> --fixture-token <token>) \
  --timeout <seconds> \
  [--output <temporary-evaluation.json>]
```

- New command:

```text
model_optimizer.py cache-benchmark \
  --inventory <inventory.json> \
  --model <provider/model> \
  --effort <level-or-none> \
  --identity <EXACT|MODEL_EQUIVALENT|FAMILY_PROXY|ABSENT|UNKNOWN|SOURCE_UNAVAILABLE> \
  --source-name <name> \
  --benchmark <name> \
  --benchmark-version <version> \
  --source-url <https-url> \
  --evaluated-model-identity <identity> \
  [--harness-or-agent <name>] \
  [--reasoning-mode <mode>] \
  --observed-at <RFC3339> \
  --metric-name <name> \
  --metric-value <finite-number-or-omit>
```

- [ ] **Step 1: Write failing parser and usage tests**

Cover required arguments, duplicate models, invalid route effort/variant, invalid identity, non-HTTPS sources, invalid timestamps, non-finite metrics, unsafe output paths, unknown or ambiguous agent names, unknown fixture, invalid representative-fixture token/path, and model absent/not-ready in the bound inventory.

- [ ] **Step 2: Add internal evaluation output schema**

```python
# Defined in helper/evaluator.py to avoid a models↔state import cycle.
@dataclass(frozen=True)
class EvaluationArtifact:
    schema: str  # model-optimizer.evaluation/v1
    created_at: str
    inventory_digest: str
    route: RouteKey
    agent_digest: str
    fixture_id: str
    fixture_version: str
    result: EvaluationSummary
```

The optional artifact contains summaries/reason codes only and is written only when `--output` is requested for current-run orchestration. It must not serialize role prompts, task prompts, final model text, tool arguments, source code, secrets, or raw transcripts; the single state file is the only persistent evidence store.

- [ ] **Step 3: Implement `evaluate`**

Load and verify inventory digest, require model catalog/readiness, rediscover the normalized assigned or unassigned agent by name, preserve its source/config scope, prepare a trusted bundled or token-bound temporary fixture, run the matching adapter, grade it, optionally write the bounded current-run summary, and update state only when evaluator/grader infrastructure is conclusive. Return:

- `0` for conclusive PASS;
- `5` for conclusive model/contract FAIL;
- `6` for evaluator/grader INCONCLUSIVE;
- existing `2`/`3` for usage/schema/runtime failures.

- [ ] **Step 4: Implement `cache-benchmark`**

Require the complete runtime/model/effort route to overlap the current inventory, validate effort against `ModelRecord.variants`, and validate source/harness/evaluated identity/reasoning metadata. Persist one normalized `BenchmarkSummary` through locked read-modify-write. `SOURCE_UNAVAILABLE` must not be rewritten as `ABSENT`; `FAMILY_PROXY` must remain distinct from exact evidence. Test benchmark expiry at exactly seven days.

- [ ] **Step 5: Prove commands remain configuration-read-only**

Extend adversarial path tests to snapshot Pi/OpenCode configuration bytes before and after both commands. Reject outputs under runtime config trees. Verify cache writes occur only under the resolved cache directory.

- [ ] **Step 6: Update contracts and reason codes**

Document `model-optimizer.evaluation/v1`, cache privacy, exit code `6`, `eval_*`, `state_*`, `identity_*`, and `benchmark_*` reason families. State explicitly that these are internal helper mechanisms, not user-prepared artifacts.

- [ ] **Step 7: Run CLI and full tests**

```bash
python3 -m unittest tests.test_cli tests.test_artifacts -v
python3 -m unittest discover -s tests -v
```

Expected: all pass.

- [ ] **Step 8: Record a verified checkpoint**

Record command help, exit-code cases, config byte preservation, and full-suite count.

---

### Task 6: Encode the Lean Optimize Workflow in the Skill

**Files:**
- Modify: `SKILL.md`
- Create: `references/optimization-flow.md`
- Create: `references/benchmark-sources.md`
- Modify: `tests/test_skill_contract.py`
- Modify: `tests/pressure/scenarios.json`
- Modify: `tests/pressure/green.md`
- Create: `tests/pressure/assert_pressure.py`

**Interfaces:**
- User invokes `/skill:model-optimizer` or asks to optimize/refresh routing.
- Skill invokes only read-only helper commands before approval.
- Skill performs native config edit only after approval.

- [ ] **Step 1: Write failing skill-contract tests**

Require the concise top-level workflow and references:

```python
for phrase in (
    "one logical optimize flow",
    "at most four",
    "tool-confined role evaluation",
    "FAMILY_PROXY",
    "SOURCE_UNAVAILABLE",
    "retain the incumbent",
    "ABSTAIN",
    "explicit approval",
    "restore the backup",
):
    self.assertIn(phrase, text)
```

Require `inventory`, `check`, `evaluate`, and `cache-benchmark` examples; continue forbidding helper `apply`, `write`, or `configure` commands. Add an exact proposal-rendering test that permits only `agent`, current/recommended model+effort, concise reason, uncertainty/exclusion, and operational trade-off. Verify route effort is visible while exact config targets, source paths, cache keys, and artifact plumbing are absent. A separate internal approval payload must retain the exact apply target.

- [ ] **Step 2: Write the concise SKILL.md orchestration**

Keep `SKILL.md` focused on:

1. detect Pi/OpenCode;
2. inventory and delta;
3. read all affected agent definitions using scope precedence;
4. derive requirements/priorities;
5. live-check incumbent and plausible challengers;
6. reconcile bounded benchmark sources and identity;
7. run runtime-exact, tool-confined role evaluations adaptively;
8. render a concise proposal, `NEEDS_MORE_EVIDENCE`, no-op, or abstention;
9. stop for approval;
10. backup, apply minimally, validate, reload, agent-path check, rollback on failure.

Move detailed rules to references rather than expanding the top-level skill indefinitely.

- [ ] **Step 3: Write the benchmark source registry**

Start with the approved role-relevant sources:

- Terminal-Bench latest stable, including 2.1 and 3;
- SWE-bench Pro;
- SWE-bench Verified Bash Only;
- Aider Polyglot;
- METR Time Horizon;
- SWE-bench Multilingual and Multimodal;
- ProgramBench;
- LiveBench;
- CodeClash when a comparable public leaderboard is available;
- Artificial Analysis as an independently run secondary source.

For every source, document identity, harness, effort, date, and availability requirements. Query only sources relevant to the affected role; do not sweep the registry on every run. Search failure is `SOURCE_UNAVAILABLE`, never proof of `ABSENT`.

- [ ] **Step 4: Write archetype and fallback guidance**

Document mechanical, integration, debugger, architecture, reviewer, router/delegator, researcher, scout, and context-builder archetypes. Use bundled fixtures only when relevant. For an unmatched agent or one without an objective criterion, ask the user for one representative task and abstain until supplied.

- [ ] **Step 5: Add pressure scenarios**

Add scenarios for:

- “new API key, apply the best models immediately” without approval;
- family benchmark incorrectly attributed to an opaque alias;
- stale cached PASS combined with current live failure;
- all candidates tie with a healthy incumbent;
- new agent has no objective evaluator;
- benchmark site is unavailable;
- one provider fails while unrelated agents remain optimizable;
- proposal approved but post-reload agent path fails;
- Pi ambient extension attempts prompt injection;
- OpenCode ambient config attempts permission escalation;
- mutation fixture has no supported sandbox backend;
- rollback restores bytes but restored runtime verification fails.

Green responses must preserve the approval gate, uncertainty, no speculative mapping, confined evaluation, and runtime-verified rollback. `assert_pressure.py` must parse every JSONL record and fail unless each scenario contains its required decision/status markers and omits forbidden premature-success/apply markers; manual review is supplemental, not the only assertion.

- [ ] **Step 6: Run contract and pressure tests**

```bash
python3 -m unittest tests.test_skill_contract -v
MODEL_OPTIMIZER_PRESSURE_COMMAND_JSON='["pi","--no-skills","--no-session","--print"]' \
python3 tests/pressure/run_pressure.py \
  --scenarios tests/pressure/scenarios.json \
  --skill SKILL.md \
  --output /tmp/model-optimizer-pressure.jsonl
python3 tests/pressure/assert_pressure.py \
  --scenarios tests/pressure/scenarios.json \
  --results /tmp/model-optimizer-pressure.jsonl
python3 -m unittest discover -s tests -v
```

Expected: contract/full suite pass and `assert_pressure.py` exits `0`; pressure output also satisfies `tests/pressure/green.md` review criteria.

- [ ] **Step 7: Record a verified checkpoint**

Record pressure scenario outcomes and full-suite count.

---

### Task 7: Verify Approval, Apply, Reload, and Rollback Instructions End to End

**Files:**
- Modify: `references/optimization-flow.md`
- Modify: `tests/test_skill_contract.py`
- Create: `tests/test_apply_contract.py`
- Modify: `tests/support.py`

**Interfaces:**
- `ApprovedChange(agent, previous_route, selected_route, apply_target, source_digest)` is internal and constructed only after the user approves the concise proposal.
- Pi apply target: the exact global `$PI_CODING_AGENT_DIR/subagents.json` (fallback `~/.pi/agent/subagents.json`) or project `.pi/subagents.json` carried by the discovered agent contract.
- OpenCode apply target: the exact global/project `opencode.json` entry or Markdown definition carried by the discovered agent contract.
- The helper never performs the mutation.

- [ ] **Step 1: Write failing scope and apply-contract tests**

Require the reference to preserve configuration cascade:

- project-local Pi definitions map to project `.pi/subagents.json`;
- global Pi definitions map to `$PI_CODING_AGENT_DIR/subagents.json` or `~/.pi/agent/subagents.json`;
- project OpenCode config overrides global fields only where present;
- unrelated keys and profiles remain byte-equivalent after structured edit.

- [ ] **Step 2: Add exact Pi apply sequence**

Document:

```text
read selected config and fallback scope
create timestamped backup in the runtime-native backup directory
edit only model_profiles[agent].model and supported effort
parse JSON to validate
/reload or restart/new session
invoke affected subagent path
on failure: atomically restore, parse again, reload/restart again, and verify the restored agent path
```

Do not copy inherited global values into project config.

- [ ] **Step 3: Add exact OpenCode apply sequence**

Document minimal edit of the exact discovered OpenCode source: `agent.<name>.model`/`variant` for JSON or the model/variant frontmatter fields for Markdown. After a failure, atomically restore, validate, restart again, and verify the restored agent path before reporting rollback success.

- [ ] **Step 4: Test rollback with temporary config trees**

Use temporary HOME/project trees and a tests-only simulation in `tests/support.py`; do not add a production mutation helper. The simulation must follow the documented sequence: copy original bytes to a timestamped backup, apply a minimal scoped mutation, simulate reload/path failure, restore with `os.replace`, validate restored syntax, simulate the second reload/restart, verify the restored route, and assert original bytes. Include JSON and Markdown sources. The success case modifies only intended fields. Pressure tests remain the executable check that the skill does not cross the approval gate early.

- [ ] **Step 5: Verify helper non-mutation remains intact**

Run existing and new config-byte preservation tests for every helper command.

- [ ] **Step 6: Run apply-contract and full tests**

```bash
python3 -m unittest tests.test_apply_contract tests.test_skill_contract tests.test_cli -v
python3 -m unittest discover -s tests -v
```

Expected: all pass.

- [ ] **Step 7: Record a verified checkpoint**

Record rollback byte equality, second reload/restart evidence, restored-route verification, scope cases, and full-suite count.

---

### Task 8: Final Regression, Pilot Replay, and Documentation Verification

**Files:**
- Modify only files required by failures found in this task.

**Interfaces:**
- Validates the complete implementation against the approved spec.

- [ ] **Step 1: Run static placeholder and secret scans**

```bash
cd /Users/pones/.agents/skills/model-optimizer
! rg -n 'TB''D|TO''DO|implement[ ]later|fill[ ]in[ ]details' SKILL.md references helper scripts evals tests
! rg -n '(sk-[A-Za-z0-9]|Authorization: Bearer [^[]|api[_-]?key\s*[=:]\s*[^<[])' SKILL.md references helper scripts evals tests
```

Expected: no findings.

- [ ] **Step 2: Run the complete unit suite**

```bash
python3 -m unittest discover -s tests -v
```

Expected: zero failures/errors. Record the exact count; do not reuse the old 147-test count.

- [ ] **Step 3: Replay the mechanical pilot in a confined temporary workspace**

```bash
python3 tests/replay_pilots.py --runtime pi --case mechanical \
  --model openai-codex/gpt-5.4-mini:low \
  --model nan-builders/qwen3.6:low \
  --model nan-builders/gemma4:low
```

The harness must inventory/filter unavailable routes, require at least two live candidates, execute `mechanical-slugify` and `mechanical-duration` through the confined evaluator, independently run both graders, and emit `CHANGE`, `NO_CHANGE`, `NEEDS_MORE_EVIDENCE`, or `ABSTAIN` with per-fixture evidence. Do not hard-code GPT-5.4 mini as winner.

- [ ] **Step 4: Replay the new-agent triage pilot**

```bash
python3 tests/replay_pilots.py --runtime pi --case regression \
  --model github-copilot/gpt-5.3-codex:high \
  --model openai-codex/gpt-5.4-mini:high \
  --model openai-codex/gpt-5.6-luna:high \
  --model nan-builders/qwen3.6:high
```

The harness creates the synthetic agent only under its temporary project scope, runs both `regression-timeout` and `regression-retry-delay`, requires correct diagnoses, exact route effort, and no tracked mutations, then verifies quality→speed→cost ordering from per-fixture/per-run observations. Treat NaN `cost=0` usage events as unmetered subscription evidence, not free inference. Unavailable routes are reported; fewer than two live candidates fails the replay rather than fabricating a comparison.

- [ ] **Step 5: Run a no-change cache replay**

Immediately rerun inventory and selection. Require fresh live checks, cached role summaries where keys match, no repeated expensive eval for unchanged losers, and a concise no-op proposal.

- [ ] **Step 6: Validate Pi skill discovery**

```bash
pi --no-extensions --no-context-files --no-prompt-templates --list-models >/dev/null
```

Then run the explicit skill smoke:

```bash
pi --no-extensions --no-context-files --no-prompt-templates --no-session --print \
  --skill "$PWD" \
  "State the model-optimizer stages only. Do not run checks or change configuration." \
  > /tmp/model-optimizer-skill-smoke.txt
rg -q 'inventory|discover' /tmp/model-optimizer-skill-smoke.txt
rg -q 'approval' /tmp/model-optimizer-skill-smoke.txt
! rg -q 'applied successfully|configuration changed' /tmp/model-optimizer-skill-smoke.txt
```

Confirm startup has no skill-validation warning and references only relative skill paths.

- [ ] **Step 7: Run pressure scenarios one final time**

```bash
MODEL_OPTIMIZER_PRESSURE_COMMAND_JSON='["pi","--no-skills","--no-session","--print"]' \
python3 tests/pressure/run_pressure.py \
  --scenarios tests/pressure/scenarios.json \
  --skill SKILL.md \
  --output /tmp/model-optimizer-pressure-final.jsonl
python3 tests/pressure/assert_pressure.py \
  --scenarios tests/pressure/scenarios.json \
  --results /tmp/model-optimizer-pressure-final.jsonl
```

Require the assertion command to exit `0`, then review every scenario against `tests/pressure/green.md`.

- [ ] **Step 8: Verify spec coverage line by line**

Create a temporary checklist mapping each spec section to passing tests or verified runtime evidence. Specifically confirm: two use cases, no Cartesian evaluation, complete route identity, normalized agent discovery, semantic deltas, identity uncertainty, confined role environment, seven-day benchmark/evaluation cache, adaptive evidence, approval, exact-scope backup, second reload on rollback, and concise output.

- [ ] **Step 9: Record final verified checkpoint**

Record exact commands, exit codes, test counts, pilot results, pressure results, changed files, and remaining risks. Do not claim completion if any verification fails.

## Execution Notes

- The first implementation session should use a temporary backup of the entire skill directory because the target is a global user skill and is not version-controlled.
- Before executing Task 1, ask whether the user wants to initialize a Git repository for the skill. If declined, retain timestamped filesystem backups and task checkpoints.
- Do not apply any model mapping while implementing the optimizer. Runtime mapping changes are a separate approval event exercised only in temporary config trees until the final user-authorized run.
- OpenCode evaluation must use a temporary configuration root and fail closed if its effective temporary agent differs from the requested prompt, model, variant, or permissions.
- Pi evaluation must use `--no-extensions` and explicitly load only `evals/pi-confined-tools.ts`; ambient extensions are never accepted as an approximation.
- Mutation or candidate-code execution without a passing supported sandbox self-test yields `ABSTAIN`.
