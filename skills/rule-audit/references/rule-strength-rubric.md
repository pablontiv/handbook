# Rule Strength Rubric — 10 Properties

Derived 2026-07-22 from the herdr guardrail (CONTRIBUTING.md:49 + AGENTS.md:235-237), a prose rule that survived 5+ turns of sustained user pressure without a hook. Extended 2026-07-23 with P8-P10 after mapping herdr's full enforcement harness (see "Enforcement layers" below). Score each rule block 0-10, one point per property. P1-P7 measure prose strength (does the rule survive the decision moment?); P8-P10 measure mechanical enforcement (does a machine catch violations regardless of agent goodwill?).

## P1 — Self-identifying trigger

The rule names its reader and situation: "If you are an AI agent helping someone with this repository...". The agent recognizes itself at the decision moment. Diffuse duties ("always X before every response") score 0: a rule that applies to every turn has no trigger at all.

Test: can you name the exact tool call or message shape that fires this rule?

## P2 — Evasion routes enumerated

The rule closes workarounds preemptively: "Do not use the GitHub CLI, API, browser automation, **or any other tool**". Each loophole the reader might argue ("I'm only building the command", "it's just this once") is already answered in the text.

Test: list 3 plausible workarounds; does the text already cover them?

## P3 — Pressure script (strongest property)

The rule contains its own response for the moment someone pushes to skip it: "If the human asks to skip the contribution process, **refuse and explain that this is how the repository owner wants contributions handled**." The agent does not have to reason about yielding — the branch is pre-resolved.

Test: does the rule say literally what to do/say when asked to skip it?

## P4 — Legitimate alternative

Prohibition plus permitted channel in the same breath: "You may help draft a short report that the human reviews and submits themselves." Pure prohibitions push readers to hunt workarounds; prohibitions with an outlet are stable.

Test: does a blocked reader know what they CAN do instead?

## P5 — Legitimacy anchor (the why)

One line of motive travels with the rule: "this is how the repository owner wants contributions handled." Arbitrary-looking rules invite relitigation.

Test: is there a one-line why, or does the rule read as decree?

## P6 — Placement nearest the action

The rule lives in the highest-precedence file the active runtime reads before the action, with redundancy only across surfaces that actually matter. Resolve precedence from the runtime's documented instruction-loading contract instead of assuming one vendor's file order.

Test: is the rule in the most action-adjacent file for the active runtime? Duplicated in the surfaces an agent actually loads?

## P7 — Applicability predicate

The rule (or its section) declares when it does NOT apply: herdr's "Scope and Audience" layer — "if the acting account is not `ogulcancelik`, skip this section." Rules that self-exclude do not dilute each other; a flat file where everything applies always makes every rule weaker.

Test: can a reader skip this rule cheaply and correctly when out of scope?

## P8 — Enforcement backstop at the correct layer

A mechanism catches violations loudly and independently of agent goodwill. But WHERE matters: a rule must anchor to the EARLIEST layer that can catch it. A backstop that only fires at release, for something a lint would catch, is too late.

Enforcement layers, earliest to latest:

| Layer | Mechanism | Catches at |
|---|---|---|
| 1 | lint config (clippy `disallowed-methods`/`-D warnings`, `#![deny]`, eslint) | the editor |
| 2 | local git hook (pre-commit, commit-msg) | the commit |
| 3 | maintenance test / script (`just check` unit tests, config-vs-doc parity, patch-index reverse-apply) | local validation |
| 4 | CI gate (fmt/lint/test matrix, path-guard, build-per-platform) | the PR |
| 5 | policy bot (auto-close unapproved PR / off-template issue) | the contribution |
| 6 | release gate (clean tree, tag absent, changelog≡docs, assets present, version match) | the release |

Score P8 = 1 only if a backstop exists AND sits at the earliest viable layer. Backstop present but too late (e.g. version drift caught only at release when a test could catch it) is a finding: "late backstop".

Test: name the mechanism and its layer. Could an earlier layer catch the same violation more cheaply?

## P9 — Executable compliance step

The rule ships the exact command/procedure to satisfy or verify it, not just a description of the obligation. herdr detection: "capture the state with `herdr agent read <pane> --source detection --format text`". Stronger than P1 (P1 says WHEN, P9 says HOW to comply right now). Bonus signal: the rule names the concrete failure the naive path causes (e.g. "`which` returns only the first match, so a shadowed old binary passed the check" — why `which -a`).

Test: does the rule embed the command/procedure, and the specific failure it prevents?

## P10 — Declaration-verification gap (hardening generator)

Not a strength score — an OPPORTUNITY flag. For any rule scoring low on P8, ask: does a cheap backstop technique exist that the repo does not use? If yes, emit a hardening proposal (rule, proposed mechanism, layer, effort). This is what turns the audit into a maintainer-proposal backlog.

Feasible-backstop patterns for common prose rules:

| Prose rule shape | Backstop | Layer | Effort |
|---|---|---|---|
| "no `unwrap()`/`panic!` in prod" | clippy `disallowed-methods` / `deny(clippy::unwrap_used)`, `#[allow]` per test | 1 | trivial |
| "use logger X, not `println!/dbg!`" | clippy `disallowed-macros` or grep-CI | 1-4 | trivial |
| "OS code isolated to dir Y" | grep-CI: forbid `#[cfg(target_os)]` outside Y | 4 | low |
| "`#[allow]` needs a comment" | custom lint / grep | 1-4 | medium |
| "commit refs #N, not closes/fixes #N" | extend commit-msg hook to reject closing keywords | 2 | low |
| "don't touch files Z on normal PR" | CI path-guard outside release branch | 4 | low |
| "state testable without <heavy dep>" | make existing invariant test mandatory in CI | 4 | low |

NOT hardenable (correctly stays prose+review): purity/no-mutation properties, evidence-based/judgment rules, "understand your code". Do not propose backstops for these; flag them as review-only.

Test: for each low-P8 rule, is there a ≤5-line mechanism the repo omits? If yes → backlog item. If it needs human judgment → review-only, no proposal.

## Known failure evidence (backscroll, calibration pending)

Dominant agent failure mode is OMISSION of pre-steps (skill loading, doc reading, delegation), not commission of prohibited acts. Prioritize P1 (concrete triggers) for pre-step duties; P2/P3 for prohibitions.

## Anti-patterns that score 0 regardless of wording

- Shaming language as enforcement ("skipping is a discipline failure") — emotion is not a script.
- ALL-CAPS emphasis as enforcement — salience without trigger decays over context length.
- Two rules in conflict (e.g. "no option menus" vs "always propose alternatives") — both lose authority; merge with a predicate.
- Project-specific content in global scope (violates P6+P7 and taxes every unrelated session).
