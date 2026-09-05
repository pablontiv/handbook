# Docs North-Star Method

Distilled from the rootline repositioning arc (2026-07): excavation → question round → runtime truth (`stem-native-discovery`) → narrative (`reposition-rootline`) → coherence pass. Use as the detailed procedure behind SKILL.md.

The single most important lesson from that arc: **the north star was never derived from the code.** It came from an owner-approved question round, and the spec quoted it verbatim as "the approved outcome". Any run of this skill that produces a hero without that approval has already failed, no matter how good the copy reads.

## 0. Excavate before forming an opinion

Repositioning a repo that already decided its identity is a recovery job, not a creative one. Sweep, in this order, and report each result:

1. **Persistent memory** — `mem_search` for north star, positioning, identity, hero, reposition; read the project memory index.
2. **Session history** — `backscroll search "<repo> north star positioning" --all-projects --indexed-only`; also search for the proposal/spec artifact names (e.g. `sdd/<change>/spec`), which surface the whole prior cycle.
3. **The repo** — `docs/**/*north-star*`, `*northstar*`, `*positioning*`, `*reposition*`, ADRs, approved design specs, `openspec/changes/`.

Possible outcomes, each with a required action:

| Finding | Action |
|---|---|
| One declared north star, still true | It is the source. Confirm with the owner, then verify the docs against IT |
| Two declared north stars (e.g. a master identity + a later feature arc) | Real fork. Surface both, ask which leads the public narrative |
| Declared north star contradicted by the owner in conversation | Owner wins. Record the contradiction; mark the spec superseded; never edit the historical spec |
| Nothing anywhere | State that explicitly, then run the full question round |

In the rootline arc the excavation covered Engram, backscroll, Pi, OpenCode, and raw Claude transcripts before concluding "no prior recorded decision existed" for the relicense. That negative result was itself reported as a finding.

## 1. The question round (gates the narrative track)

This round gates the spec, the copy, and every file edit. It does NOT gate excavation or verification — those run on the evidence track, which never queues behind an unanswered question. When the round cannot close, the audit still ships; only the narrative stops.

Keep the asymmetry straight: **gathering evidence needs no owner; deciding what it means does.** A sweep can be completed alone, and its findings reported alone. Concluding that a north star it surfaced still holds, or that a hole in the sweep is a real absence, is a narrative-track judgment and belongs to this round.

The owner approved "an interactive product-question round before creating the proposal … to clarify the business outcome, target audience, scope boundaries, and tradeoffs before freezing the proposal." Reproduce that. Ask discrete questions, one at a time, and stop for each.

1. **Business outcome** — "what changes for someone after they adopt this?" Push until the answer is a transformation, not a feature list.
2. **Audience & trigger** — who has this problem, and what makes it start hurting. Complexity is usually the trigger; team size usually is not.
3. **Scope boundaries** — what the product explicitly is NOT. (rootline: not an agent runtime.)
4. **Negative space** — which adjacent tech, vendor, standard, or ecosystem partner must NOT appear in the hero. (rootline: OKF excluded from the narrative entirely; Git demoted to optional integrations.)
5. **Tradeoffs** — what the positioning gives up.

Close by proposing hero + support wording and getting explicit approval of the **exact words**. Proposing is required — nobody can approve an abstraction — but the proposal must be built from the owner's own answers, presented as a candidate, and marked unapproved until they accept it. Two or three candidates with the tradeoff between them stated is a good round; one candidate asserted as settled is the failure. Once approved, quote it verbatim everywhere downstream and never paraphrase it — the spec requirement is that both approved lines appear verbatim.

**Deriving a hero from the code instead of asking is the skill's known failure mode.** A repo's source can tell you what it does; only the owner can tell you what it is for and what it refuses to be. The distinction that matters is not "propose vs. stay silent" — it is "propose from their answers, awaiting approval" vs. "assert from your reading of the code".

### Hero shape

`"<Product> turns <raw input> into <governed outcome>."` — e.g. "Rootline turns Markdown into a governed, queryable knowledge system."
Support line, for the ongoing benefit: "Keep your X consistent, connected, and queryable as it grows."

Ground every abstract positioning word immediately. "Governed" means nothing until paired with inherited schemas, validation, relationships, explainable origins. Order matters: trust foundation first (governance), practical payoff second (queryability).

## 2. Validate the pains against evidence

Find the 2–3 recurring pains the product demonstrably solves. A pain is "verified" when real usage, issues, or history show it — not when it sounds plausible. The rootline round went further and checked whether both pains (structural consistency as knowledge grows; selecting relevant knowledge for a task) were persistent in the wider community before settling on them. Do that when the positioning is public-facing.

## 3. Runtime truth and the scope split

Run the product in the environment the promise implies, **including the adversarial one**: a fresh install in a directory without the thing you claim is optional. The rootline smoke test in a non-Git directory found `query`/`graph` fine, `validate <file>` broken, and `validate --all` exiting 0 over zero records — a false green that no amount of README editing could fix.

**Verification is re-entrant, because `claim ≤ behavior` has two sides and both move.**

*The claim side.* If the sweep ran before the hero was approved, it probed the claims the docs already made — not the ones the new promise makes. Approving a hero creates uncovered claims by definition: new language, written to be attractive, describing behavior nobody has checked in those terms. Before any spec consumes the gap list, subtract what was already verified from what the approved promise asserts and probe the remainder. An empty delta is a finding to state, not an assumption to make.

*The behavior side.* The prerequisite change exists precisely to move the runtime, so the moment it lands every conclusion the sweep drew about the behavior it fixed is obsolete. Blocked doc slices resume only after re-verifying the claims that change was supposed to enable — in the rootline arc, running the Gitless scenario again after `stem-native-discovery` shipped, not inferring from the release that it now worked. A prerequisite that shipped is a reason to re-probe, never evidence of the outcome.

*Coverage is not currency.* A gap list can be perfectly up to date and still carry claims nobody could check — no safe environment, no runnable form. Those may be omitted, narrowed to what was verified, or marked in-development; they may never be asserted as fact in the spec.

**A disproven claim is not queued behind an engineering cycle.** The gates in this method exist to stop unagreed claims going *in*; making a *demonstrably false* published claim wait out a prerequisite cycle inverts their purpose and keeps readers misled meanwhile. So correcting one is expedited — but expedited is not ungoverned, and the exemption is narrow on four axes:

- **Only demonstrably false, never merely unverified.** "We ran it and it does not do this" qualifies. "We could not check" does not: unverified means unknown, and deleting documentation that is probably true harms the people relying on it. Unverified claims stay, flagged, pending verification.
- **Only living surfaces.** The record — ADRs, archived change artifacts, git history — is never edited to match the present, false or not. It gets a superseding note; the rule above it does not bend.
- **Never the hero or positioning copy.** A disproven hero claim is a product decision, so it returns to the question round for new approved wording. The expedited path is for ordinary documentation claims, not for what the product says it is.
- **Smallest span, and nothing new asserted afterwards.** Target the falsehood, not the section around it. Then check the result: the docs may claim only what they already claimed *and* verified. Nothing is added — not even a note that the thing does not work, which is still a sentence about something the living doc no longer needs to mention at all. That leaves three permitted edits: delete the false span; narrow it to a subset of what was already verified; or, when the subject still exists but is unproven, mark it in-development. Writing a corrected sentence is *not* a retraction: it is new copy, unapproved and quite possibly unverified itself, arriving through a door built for removals. Route replacement wording through approval like any other claim.

Everything else still waits its turn, and no path here authorises an unattended run to write.

Split the findings:

- **DOC gaps** — copy is wrong; belongs to this change.
- **BEHAVIOR gaps** — the runtime cannot back the promise; becomes a **separate prerequisite change** with its own cycle, which **blocks** the doc slices.

The owner explicitly excluded the Gitless correction from the repositioning change; it shipped first as `stem-native-discovery` (released as a major), and the doc slices stayed blocked until it landed. That ordering is the rule, not a one-off: narrative never ships ahead of behavior, and behavior fixes never hide inside a docs change.

## 4. Claim verification procedure

Every documented claim names an **invocable unit** — the smallest thing a reader could try. Identify the repo's artifact type first (SKILL.md Phase 2 table) to know what that unit is: a command+flag for a CLI, an exported symbol for a library, an endpoint for a service, a user flow for an app, a config key for infra, a cross-reference for a content repo. A repo may be several types at once; sweep each.

Generic source precedence, instantiated per type:

1. **Declared interface** — the artifact's own self-description: `--help` for a CLI, the public API surface for a library, route/schema definitions for a service, the config parser for infra.
2. **Source code** — definitions, defaults, output shapes; and for anything that looks like a feature, a real *consumer* of it, not just a definition.
3. **Accepted tests** — the scenario is exercised and the output shape matches.
4. **Representative execution** — run it and capture ACTUAL output, never inferred, and only where running is safe: local, disposable, or an explicitly-designated test environment. Verification never mutates shared state — no production requests, no applied infra, no writes to shared data, no disabling a safety check to make a claim checkable. Where only a shared environment exists, stop at the highest read-only level and mark the claim unverified with that reason.

Unverifiable claim → omit entirely, mark "in development" with a link, or narrow to what is verifiable. When the repo offers no runnable form at all (no build, no fixtures, no environment), stop at the highest precedence level available and report the claim as unverified with the reason. Unverified is an honest finding; assumed-correct is a defect.

**Ghost sweep**: extract every invocable unit mentioned across docs and agent skills; exercise each. Findings classify as: correct / stale (behavior changed) / ghost (no longer exists, or never did). **Ghosts are deleted from the living doc** — not annotated as removed, not replaced with a pointer. Whether it once existed is a question about the past, git answers it, and the living doc has no business carrying the answer. This also disposes of a question you often cannot settle: "removed or never there?" stops mattering when the edit is the same either way. "Deprecated" is sayable only when the deprecated path still works today — that is a fact about the present, so it belongs.

Three consecutive review rounds on one README each caught a claim that was syntactically verified and semantically false. Every documented command and flag had been executed against a dev build and every one existed — and the page still promised persistence the sync path contradicted (append-only held for 41% of rows), an output surface five of ten commands lacked, and a linkage that differed per platform. Existence checks are necessary and never sufficient; pair them with the quantifier sweep, which targets exactly the sentences whose truth depends on a complement nobody enumerated.

**Version pins**: living docs carry no product-version pins ("while in v0.x", "since libfoo v0.5"). Version history belongs to git. Toolchain minimums that mirror a manifest (go.mod) are allowed.

## 5. The spec shape

**Approval is a state, not a stamp.** Both gates — hero and spec — bind to the exact content approved and to the inputs it rested on. Any of them moving lapses the approval: a re-probed gap list, a revised requirement, a reworded hero. Re-obtain it before proceeding. The asymmetry worth internalising: an approval you already hold feels like progress you own, which is exactly why a quiet revision under it is the easiest way to ship something nobody agreed to.

When the runtime disproves a claim the approved hero makes, the hero changes — not the evidence, and not the reader's expectations. Go back to the question round with the finding. The runtime always gets the last word on what the promise may say.

The deliverable is a change spec, not a report. Shape it as testable requirements:

```
## Purpose
Define a truthful, outcome-led documentation contract for <Product>
without changing product behavior.

## Requirements

### Requirement: Lead With the Approved Outcome
The README MUST lead with "<approved hero verbatim>" and MUST immediately
support it with "<approved support line verbatim>".

#### Scenario: Approved opening
- GIVEN a reader opens the README
- WHEN the primary message is displayed
- THEN both approved lines appear verbatim and before detailed capabilities
```

Minimum requirement coverage, each with its own scenario:

- lead with the approved outcome (verbatim);
- frame growth/complexity without audience segmentation;
- establish the value hierarchy (trust foundation → practical payoff), grounding every abstract word;
- position consumers without redefining the category (humans, automation, and AI agents are consumers; the product is not an agent runtime);
- keep optional context out of the core narrative (named vendor/standard excluded; adjacent tech labeled optional where it appears);
- provide progressive, verified proof (outcome → short executable proof → concepts → capabilities → optional integrations → references);
- bound every technical claim (no universal JSON/version claims, no autonomous-repair guarantees, nothing unverifiable).

Follow with a **surface inventory** (every file, with why) and **slices** that each preserve the full message hierarchy.

## 6. Message hierarchy (README)

One continuous arc, delivered in slices that each preserve the whole hierarchy:

1. **Hero & Promise** — hero + support + 2–3 sentence outcome tied to the pains.
2. **Why It Matters / Proof** — 3–5 concrete benefits; short command proof.
3. **Core Concepts** — WHAT the product models before HOW it works; defer mechanism detail to reference docs.
4. **Capabilities by use case** — outcome-named groups, each showing the outcome first, then commands.
5. **Optional Integrations** — adjacent tech lives here with an explicit "X is optional" statement, verified.
6. **References** — grouped by audience (user / integrator / contributor).

## 7. Agent instructions are a separate executable surface

- Skills/CLAUDE.md routing tables, flag sequences, and workflow examples are runtime contracts: a wrong row breaks an agent at execution time (rootline case: `fix … -o json` piped to `repair apply` without the redirection step = guaranteed failure).
- Verify them separately from human prose: run each routed command; check report-file semantics (e.g. tools that resolve paths relative to a report's directory).
- Watch for the inverse drift too: an agent skill can be MORE current than the README (backscroll case — the skill documented the shipped `patterns` census commands while the README still sold v1 search). Whichever surface is stale, they must end the change telling one story.

## 8. Truth mechanics for satellite surfaces

- **Coherence set**: repo description = hero line; README badge ⇄ LICENSE file ⇄ License section ⇄ agent skills — one story, no contradictions. GitHub only auto-detects canonical license texts (verbatim Apache-2.0 detects; PolyForm shows "Other").
- **Roadmap truth**: record states reflect reality. Work superseded by a decommission decision → `Obsolete`. A status field is current fact *about the record*; that is why it is set rather than deleted, and it does not conflict with deleting product claims that no longer hold. Use the product's own tooling to mutate records when it has one (dogfood).
- **Never rewrite the record**: archived change artifacts, completed task records, and ADRs are never rewritten to match the present — fidelity of history outranks tidiness. A superseded identity statement gets marked superseded, not edited. Archive copies must be byte-faithful (diff them; agents that "archive" by rewriting lose content).
- **Enforcement**: a pre-push docs-sync guard (config/CI/manifest change requires README, docs/, or CLAUDE.md in the same push) keeps drift from re-accumulating. When a guard predates a surface it should cover, fix the guard rather than bypassing it.

## 9. Audit tooling gotchas

These are CLI-specific traps, hit hard in the rootline and backscroll sweeps. For a library, service, or content repo, the equivalent traps live elsewhere (flaky fixtures, an unreachable staging environment, generated API docs regenerated from a stale branch) — the transferable rule is that the sweep's own tooling can manufacture false results, so validate the sweep before trusting its findings.

- **Self-updating binaries hang sweeps**: a CLI with auto-update may hit the network on every invocation; a loop of `--help` calls times out. Build a local dev binary (version injection skips update checks) and sweep against that, or set the tool's update-disable env var.
- **macOS has no `timeout`**: GNU `timeout` is absent (rc=127); use a background-process watchdog (`cmd & … kill -0 … kill -9`) for hang bisection.
- **Extract, then diff**: capture every `<cmd> --help` to files in parallel, extract the real flag surface, and diff against flags mentioned in docs. Filter markdown table separators (`---`) and prose before judging; verify each survivor's line context — cross-references to OTHER commands' flags are valid.
- **JSON contract check**: run each command with JSON output and compare `version`/`kind` fields against every documented example AND global claims ("all commands emit version N" fails the moment one contract bumps).
- **Dead config is a ghost too**: config blocks that parse but are never consumed (an `[embedding]` section whose provider is never wired) read as features. Grep for a production caller, not just a definition.

## 10. Case study anchors

**rootline 2026-07 (the full arc)**

- Owner-approved question round preceded the proposal; the spec then required the approved lines verbatim.
- Runtime blocker split out: `stem-native-discovery` shipped first (major release), `reposition-rootline` slices 2–7 stayed blocked behind it.
- Ghost command: skill listed removed `apply` as "deprecated" with a warning message that could never print.
- Fossilized doc: CLAUDE.md explained "Pre-1.0 v0.x" bump rules while the repo shipped v4.
- Fabricated example: stats docs showed populated aggregation maps; source initialized them empty by design.
- Mislabel: `graph -o json` documented as DOT output.
- Sequencing win: Gitless discovery shipped before the README said "Git is optional" — narrative never exceeded behavior.

**backscroll 2026-07 (excavation failure, corrected)**

- The skill v1 went straight to "derive hero" and invented one, while TWO approved north-star specs sat in `docs/superpowers/specs/`. The owner caught it: "esperaba preguntas, ¿sabemos cuál es el northstar?"
- A declared spec can also be stale: the master design locked identity as "complements engram", and the owner later corrected it to standalone. Owner overrides spec; the spec gets marked superseded, not rewritten.
- Both failures trace to the same missing gate — no excavation, no approval. Hence Phases 0 and 1.
