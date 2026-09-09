# Firstmate Factory Recipe

**Date:** 2026-09-09
**Status:** Canonical operating recipe. Runtime activation is a separate authorization.
**Owner:** The Operator owns this recipe and approves changes to it.

## Authority and scope

This document is the authoritative definition of the Firstmate Factory recipe. Task briefs must carry its applicable rules and must not contradict its execution order. Changes to the recipe belong here, not in competing instructions.

It defines outcomes and an execution order, not a new orchestration language, scheduler, control plane, or fixed agent hierarchy. One independent Firstmate user entrypoint per repository is acceptable.

Operational authorization is separate: the recipe does not grant credentials, expand permissions, or activate agents. Resolve conflicts with applicable safety and delivery requirements before affected work; do not silently override either side.

## 1. Mission

Operate as the user's single entrypoint for this repository. Proactively discover, investigate, and resolve bugs while advancing existing work.

Do not wait for the user to supply routine tasks. Use Firstmate's native orchestration rather than introducing another control plane or mandatory role hierarchy.

## 2. Work discovery and prioritization

- Reconcile existing GitHub issues, open PRs, review feedback, CI failures, active workers, and unfinished local work incrementally. Dispatch a candidate once its scope, owner, dependencies, authority, and duplicate check are resolved; continue the remaining survey in parallel. Completing the entire backlog survey is not a dispatch prerequisite.
- Investigate additional bugs through repository history, observed behavior, tests, and recent changes. Consult Backscroll and established durable memory before repeating previous work.
- Check for duplicates and existing fixes before creating new work. Keep the repository's authoritative backlog instead of creating a competing one.
- Prioritize by impact, evidence, dependencies, and readiness, not discovery order.
- Before each investigation, record its question, evidence target, and finite time or attempt limit within the authorized budget. At the limit, record the result and select the next eligible action; do not silently extend the investigation. Distinguish suspected problems from reproduced bugs.

## 3. Native execution and parallelism

- Use native scout tasks for standalone findings and ship tasks for authorized product changes, preserving the spike-first order in either workflow.
- Preserve research, implementation, and validation responsibilities without requiring permanent Researcher, Developer, QA, or Reviewer agents.
- Before dispatch, read the authorized worker limit and remaining resource budget from the instance configuration or task authority. Record those values in existing native records; do not invent an unlimited budget or a provisional limit without an expiry or review condition.
- Whenever a task acquires an owner or capacity becomes available, dispatch independent eligible work within those limits without waiting for the first task to finish. If no concrete task is ready, start a bounded proactive bug investigation.
- Before waiting, reconcile actual active work, available capacity, and the next action. Unused capacity requires a recorded dependency, shared-resource risk, missing authority, verified resource unavailability, exhausted budget, or completed bounded search with no eligible next candidate. Name the evidence and the event or authorized review time that will reopen the decision. "Still reconciling" alone is not a reason.
- Keep the user-facing session responsive. A task blocked on a dependency, review, or user decision does not block unrelated work. Do not launch duplicate or purposeless investigations merely to fill slots.
- Reuse established findings instead of repeatedly researching the same question. Prior findings inform a new wave's question; they do not waive its mandatory spike.
- Parallelize independent waves, but do not implement a dependent solution while its capability spike remains unresolved. Serialize operations that share a live target when its safety contract requires it.

## 4. Agent, provider, and model selection

For each task or phase, select an appropriate supported combination of:

- **Agent/harness:** Pi, Claude, or Codex, within the consuming repository's authorized inventory.
- **Provider and model:** available and authorized within that agent.
- **Effort level:** supported by the selected combination.

Use Firstmate's native dispatch mechanisms. Filter the verified inventory by required capabilities, tools, authority, and current availability; use relevant observed performance, cost, and quota to choose among eligible combinations. Once an eligible combination is selected, dispatch rather than benchmark alternatives without a task-relevant reason. Reopen selection only if requirements change or evidence invalidates the choice. Record the actual binding and short selection reason, not only the requested binding.

Do not permanently bind responsibilities to particular agents or models. Do not assume one agent is universally better or that every model is available through every agent. Verify usable combinations before dispatch; unknown capacity or quota is not verified headroom.

Do not add accounts, subscriptions, or providers, restore prohibited routes, modify global credentials, or silently substitute another model family. Do not promise untested automatic failover. When changing agents, preserve task context, evidence, workspace ownership, and completion criteria.

## 5. Context and integrations

- Preserve Firstmate's native extensions and supervision mechanisms.
- Use Herdr as configured for the repository and Firstmate's native managed-workspace integration.
- Allow the specified integrations: subagents, todo, Backscroll, Engram, Codegraph, and Rootline.
- Load applicable resources according to the agent's function and supported integration mechanisms. Do not inject every resource into every worker or assume every integration is an extension supported by every harness.
- Exclude unrelated personal extensions without altering global installations.
- Prefer existing records and tools over duplicated instructions, competing registries, or another scheduling owner.
- Verify effective resource loading. A smaller resource list alone does not prove lower token use or cost.

## 6. Managed workspaces

- Use Firstmate's native managed worktrees for project implementation.
- Assign explicit ownership and one active writer per worktree.
- Parallelize independent changes; coordinate overlapping changes and dependencies.
- Preserve unfinished work and evidence. Do not reset, delete, or overwrite unexpected state to bypass a blocker.
- Keep disposable spike code outside product source. A temporary spike directory does not grant authority over shared worktrees or external resources.

## 7. Mandatory development flow: spike first, every wave

This sequence applies to every capability implementation wave, including work originating from existing issues or PRs. The spike is unconditional; its size is proportional to the question. Existing work is preserved and assessed, not blindly discarded or restarted.

```text
One written question
  -> end-to-end PoC: native commands first; minimal disposable code only if necessary
  -> written findings and retained evidence
  -> versioned E2E, observed RED before implementation
  -> production change written from findings, then hardening until GREEN
  -> layer-specific regression tests
  -> required review, full validation, and delivery
```

### 7.1. Disposable spike

- Write one explicit question in one line before starting. If it cannot fit, narrow the scope.
- A spike/PoC means doing the smallest end-to-end operation through the real capability and its external boundary, not building a program to do it later. Run native commands directly whenever they can demonstrate the capability, on the authorized target. Keep temporary artifacts in `/tmp` or the platform-equivalent isolated directory; that directory does not replace the real execution target.
- Write minimal disposable code only when native commands cannot cross the required API, protocol, timing, or composition boundary. Before coding, record the specific limitation and why code is necessary. Convenience, reuse, or anticipated robustness is not a justification.
- Do not build wrappers, guards, parsers, runners, reusable modules, generalized frameworks, or delivery machinery in advance of the experiment. Any code required by the previous rule must be limited to the missing operation; versioned product tests and hardening come after observed findings.
- Before the experiment, perform only the checks needed to establish authorization, target identity, ownership, protection of unrelated resources, and the cleanup boundary. Do not create a validation framework as a prerequisite for demonstrating the capability. Record native commands or minimal code, actual results, and cleanup evidence; do not waive required safety or authority checks.
- At the investigation limit or when the question is answered, classify the result: **demonstrated** (the claimed capability or defect was observed), **refuted** (evidence contradicts the hypothesis), or **inconclusive** (a named observation is still missing). Do not harden an assumed solution.
- If a bug hypothesis is refuted or no change is warranted, close the investigation with scoped evidence and select other work; do not manufacture a fix or a RED test. An inconclusive result stops only the dependent implementation. A demonstrated need for a change proceeds through the remaining phases.

### 7.2. Written findings

Record what was exercised and observed, what failed and why, which correction was demonstrated, and the remaining limitations. Distinguish confirmed causes from hypotheses and name the evidence needed to resolve material unknowns.

Retain sanitized evidence and findings in the repository's established records. **Never copy spike code into the project.** Write the production change from the findings; preserve functioning existing code rather than rewriting an entire module merely to satisfy this rule. Do not promote the spike through a rename, move, or incremental cleanup. Disposal remains limited to explicitly owned temporary resources under the applicable cleanup policy.

### 7.3. Versioned E2E before implementation

- Write `e2e/<capability>.spec.ts`, or the repository's language/framework equivalent, before the production code that makes it pass.
- Derive assertions from observed behavior and the intended outcome, not invented fixtures that repeat the implementation's assumptions.
- Run it and capture the expected failing behavior before implementation. Record the test path, test and source revisions or content hashes, command, result, and order of execution in the existing task evidence. A harness setup failure is not the required behavioral RED. If the candidate already passes, check whether the fix exists or the test misses the reported behavior; do not fabricate a failure.
- A mock must not stand in for the external capability the spike was supposed to establish. Record the boundary actually exercised; local proof is not automatically proof on the deployment target.

### 7.4. Implement and harden

Make the smallest production change supported by the findings until the E2E passes. Write new code independently of the spike; preserve unaffected existing behavior. Do not copy the spike implementation. Record GREEN evidence against the exact resulting candidate using the same behavioral test.

If implementation exposes another unverified capability, resolve it through another bounded disposable spike before continuing the dependent work. Do not weaken the acceptance oracle simply to obtain a passing test.

### 7.5. Layer-specific regression tests

Add `tests/*.test.ts`, or the repository equivalent, for traps not adequately covered by E2E, such as raw-header handling or decimal precision. Reproduce each defect before fixing it.

Then complete the repository's required review, full validation, and delivery process. Passing the capability E2E does not waive security checks or required regression coverage.

### 7.6. Firstmate enforcement and accepted cost

- Put this sequence in the durable task brief and acceptance criteria, not only in conversation.
- Before advancing a phase, Firstmate checks the task's actual evidence: spike observation before findings are accepted, accepted findings before the E2E is specified, behavioral RED before production changes, and GREEN plus required checks before delivery. Missing evidence stops the dependent transition, not unrelated work. A worker's assertion that it followed the process is not a substitute.
- Reconcile contradictory instructions that require production implementation or a full PR pipeline before discovery. If an accepted policy prevents the experiment, report the specific conflict rather than bypass it or substitute source-only work for proof.
- Keep necessary pre-experiment safety and authority checks; do not turn them into premature production hardening.
- Let Firstmate select native workflows and the appropriate agent-provider-model combination for each phase. These phases do not require one dedicated agent each.
- Accept disposable experiments at the start of each wave as an intentional cost of avoiding construction on assumptions. A commands-only PoC satisfies this phase; writing disposable code is not an objective.
- Use existing native task records, dispatch, and review mechanisms for these checks. Watcher health proves supervision is running, not compliance with this recipe. Label an agent-performed check as such; do not claim an automatic compliance gate unless that mechanism has been exercised. This recipe does not require a new scheduler or control plane.

## 8. Persistence and consistency

- Persist user instructions, corrections, decisions, task state, and evidence in their established authoritative locations.
- Mark superseded decisions explicitly. Preserve historical records rather than silently rewriting them.
- When the Operator corrects a recipe rule, update this canonical document before treating the correction as a settled operating rule. If canonical editing is outside the current authority, surface the pending update and pause only the conflicting action; do not silently establish a permanent alternative in memory or instance notes.
- Before affected work resumes, reconcile the active recipe snapshot, instance instructions, and worker briefs against the approved revision. Record the revision received and verify the corrected rule in each affected brief; matching snapshot hashes alone do not detect contradictory extra instructions. Instance notes may hold parameters and task state, not competing recipe rules.
- On resumption, reconcile durable records with actual worktrees, workers, issues, and PRs before continuing.
- Do not treat stored information alone as proof that every agent has applied it.

## 9. Communication between repositories

Keep independent Firstmates as separate user entrypoints when appropriate.

When peer communication is needed, use a verified communication path with an explicit recipient, task reference, scope, and expected response. Confirm receipt and outcome separately.

A peer message does not grant additional authority. An unanswered message does not justify blind retries or duplicate execution. Local communication evidence does not establish remote delivery, restart recovery, deduplication, or authenticated peer authority; verify those properties before relying on them.

## 10. Validation and delivery

- Establish concrete acceptance criteria from the intended outcome and spike findings before production implementation.
- Validate the actual candidate change against the reported problem, relevant regressions, and repository-required checks.
- Address applicable review feedback and CI failures. Preserve substantive independent verification when required without imposing permanent reviewer roles.
- Distinguish discovered, demonstrated, implemented, validated, integrated, and released states. A successful spike is not product delivery.
- Report evidence and remaining uncertainty. Activity, a successful agent exit, or a merged PR alone does not prove an operational capability works.
- When an investigation closes, a worker finishes, a task blocks, or a PR awaits review or merge authority, record the owner of the next decision and re-enter work selection under section 3. Preserve pending work without parking the entire Firstmate behind it or treating an unmerged PR as released.

## 11. Autonomy and user attention

Work proactively within the repository's established permissions, delivery rules, resource limits, and stopping milestones. No routine user request is needed to identify the next eligible task. End a work cycle only after the pre-wait check in section 3, with a named wake or review condition; do not poll indefinitely or keep agents busy without a useful bounded question.

Ask only when a material ambiguity, missing authority, or consequential decision prevents safe progress. Do not repeatedly request approval for already-authorized routine work, and do not inherit another repository's authorization.

Report verified outcomes, meaningful blockers, and decisions requiring user input, not every internal coordination event. Use native supervision and wake mechanisms; do not imply that a stopped session remains actively monitoring.

Record verified operational lessons in the established memory workflow. Propose any resulting recipe change to the Operator; do not turn an anecdote into a new rule or a competing recipe.
