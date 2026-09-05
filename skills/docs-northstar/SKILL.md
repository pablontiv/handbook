---
name: docs-northstar
description: "Trigger: north star, northstar, reposition repo, vender el producto, documentación orientada, README rewrite, docs audit, documentation drift, stale docs, ghost commands. Excavate or elicit a repo's north star, validate it with the owner, and emit a change spec that aligns every doc surface to verified behavior."
license: Apache-2.0
metadata:
  author: "pablontiv"
  version: "3.3"
---

## Activation Contract

Use on ANY repository when defining, recovering, or refreshing its product narrative (north star, hero, README restructure), or when auditing documentation that drifted from actual behavior. Covers every living doc surface: README, docs/, agent instruction files, agent skills, roadmap, LICENSE, and repository description. Not for prose style alone.

**The north star is a product decision, not a derivation.** This skill discovers it or elicits it from the owner. It NEVER authors one unilaterally.

## Hard Rules

- **Never invent a north star.** Phase 0 excavation is mandatory; Phase 1 elicitation blocks the narrative track (spec, copy, edits) but never the evidence track. Proposing candidate wording drawn from the owner's answers is required; **asserting, shipping, or writing into any file** a hero the owner has not approved verbatim is the failure mode this skill exists to prevent. If you cannot point to the answer each phrase came from, you are inventing.
- **Hero = outcome transformation** ("X turns Y into Z"), plus one support line for the ongoing benefit. Never define the product by adjacent tech (a VCS, an AI runtime, an editor), a format standard, a vendor, or team size — complexity is the audience trigger; adjacent tech goes to an Optional Integrations section; AI agents are consumers, not the category.
- **Behavior before narrative**: any claim the runtime cannot back becomes a SEPARATE prerequisite change that BLOCKS the doc change. Never fold a runtime fix into doc scope, and never let positioning ship ahead of behavior.
- **Claim ≤ behavior**: verify every documented invocable unit — command, flag, symbol, endpoint, config key, cross-reference — against (in precedence) its declared interface → source (a real consumer, not just a definition) → tests → safe representative execution. Unverifiable → omit, mark in-development, or narrow. A unit that no longer exists is deleted from the living docs.
- **A correction inherits the discipline of the claim it replaces.** When a universal fails, the reflex is to assert its negation, and the negation is usually just as unverified — measured on one platform, one branch, one sample. In order of preference: drop the claim if it is not load-bearing; narrow it to the case actually measured; or verify every case and state the split. Asserting the opposite universally is never one of them.
- **Living docs state what is, and only that.** Anything that no longer exists is deleted, not annotated as gone — history lives in git. No product-version pins ("while in v0.x", "since libfoo v0.5"); toolchain minimums mirroring a manifest are fine. "Deprecated" is sayable only when the deprecated path still works today, because that is a fact about the present.
- **Never rewrite the record**: archived change artifacts, ADRs, and completed task records are never edited to match the present. A superseded decision gets marked superseded, not rewritten.
- **Agent instructions are executable contracts**: verify skill and agent-instruction claims against real behavior separately from human prose, and synchronize them in the same change.

## Decision Gates

| Situation | Action |
|---|---|
| A north star already exists in the repo or memory | It is the SOURCE. Verify it still holds with the owner; never replace it silently |
| Two declared north stars, or one contradicted by the owner | Real fork → surface it and ask which leads. Mark the loser superseded |
| No north star found anywhere | Run the full question round (Phase 1). Do not derive one from the code |
| Owner corrects a declared identity | Owner wins over any spec. Record the contradiction; do not rewrite the historical spec |
| Runtime cannot back the promise | Split: prerequisite change (behavior) BLOCKS doc change (narrative) |
| No hero / mechanism-first README | Restructure: Outcome → Proof → Concepts (what it models before how it works) → Capabilities by use case → Optional Integrations → References by audience |
| Abstract positioning word ("governed", "unified", "intelligent") | Ground it immediately in concrete verified controls, or cut it |
| Claim unverifiable in minutes | Run the real command / read source before writing |
| Roadmap describes decommissioned work | Set the record's state to Obsolete — a status field is current fact about the record, not a claim about the product |
| Config/CI change without doc update | Same-push docs update (pre-push guard) |

## Execution Phases

The phases run on two tracks, and only one of them can be blocked. **Phase numbers are dependency labels, not a required execution order.**

- **Evidence track — Phases 0 and 2.** Gathering and verification need no owner, so this track never queues behind an unanswered question. Phase 2 may run concurrently with Phase 1, or entirely ahead of it; in a report-only run it runs without Phase 1 at all. It produces findings, never copy. **It is re-entrant**, because `claim ≤ behavior` has two sides and both move: an approved or changed hero introduces claims the earlier sweep never covered, and a runtime change — above all the prerequisite change landing — invalidates what the sweep concluded. Coverage does not exist until Phase 2 runs again over whichever side moved.
- **Narrative track — Phases 1, 3, 4.** Strictly ordered among themselves and gated by the owner at two points: the **hero wording** at the end of Phase 1, and the **spec** at the end of Phase 3. Phase 3 additionally consumes the Phase 2 gap list, so it waits on both.

"Blocking" therefore means *blocks the narrative track*, never the evidence track. An unanswered question round stops the spec, the copy, and every file edit — it does not stop the audit.

One asymmetry to keep straight: **evidence gathering is owner-independent, but confirming what the evidence means is not.** Phase 0 can sweep every source alone; deciding that a north star it found still holds — or that a gap in the sweep is a real absence — is a narrative-track act that belongs to Phase 1.

Each phase has an entry condition and something that invalidates its output. Check both before starting a phase and before consuming its result:

| Phase | Requires | Output invalidated by |
|---|---|---|
| 0 Excavate | nothing | a source becoming available that the sweep could not reach |
| 1 Question round | Phase 0 report, a reachable owner | the owner changing an answer |
| 2 Verify | a claim set to probe (the approved hero, else today's documented claims) | **either side of claim ≤ behavior moving**: a hero approved or changed after the sweep, or the runtime changing under it (notably the prerequisite change landing) — re-probe the affected claims |
| 3 Spec | approved hero + a gap list both **current** (nothing moved since) and **complete** for every claim the spec will assert | either input changing, or an asserted claim turning out unverified |
| 4 Deliver | a spec that is approved **and still valid** — same content, same inputs, as of now | the spec changing, or either of its inputs moving (both lapse the approval) |

**Approvals bind to content, and they lapse.** An approval covers the exact words approved and the inputs they rested on; it is not a permanent property of the artifact. If the hero changes, the gap list is re-probed, or the spec is revised for any reason, the prior approval **lapses** and must be obtained again before anything downstream proceeds. "Approved once" is not "approved" — a silently revised spec licenses edits nobody agreed to, which is the hero failure mode moved one gate down.

**Expedited correction path.** The gates stop unagreed claims going *in*; they must not trap a **disproven** claim inside, waiting out a prerequisite or an approval while readers are misled. Correcting one therefore skips the queue — expedited, not ungoverned. It applies only when every axis below holds:

| Axis | Qualifies | Does not |
|---|---|---|
| Evidence | ran it, it does not do this | could not check — *unverified is unknown, not false; deleting probably-true docs harms whoever relies on them* |
| Surface | living docs | the record — ADRs, archived change artifacts, git history — never edited to match the present |
| Subject | ordinary documentation claims | the hero or positioning copy — a disproven hero is a product decision and returns to Phase 1 for new approved wording |
| Extent | the smallest span that removes the falsehood | deleting the surrounding section — a retraction that removes more than the falsehood is its own drift |
| Result | every surviving claim was already there **and** verified | any new assertion, however small or however obviously true it looks — including narrating what the removed text used to say |

**The test for the Result axis**: after the edit, the docs may claim only what they already claimed *and* what was verified. Nothing is added — not even the disproof, because "this does not work" is still a sentence about something the living doc no longer has any reason to mention. Three edits pass:

- **delete** the false span;
- **mark** it in-development or under-verification — available only for something that still exists but is unproven. Never use a mark to narrate a disappearance: "removed" claims the thing once existed, and a living doc does not carry what a thing used to be;
- **narrow** it to a subset of what was already verified.

Anything else is authoring replacement copy. That is an addition — the exemption is for taking claims back, and writing a corrected sentence is not taking one back. Route it through approval like any other new claim.

Anything failing an axis takes the normal route. Nothing here authorises an unattended run to write.

What each gate governs:

- **Proposing** candidate hero/support wording is not only allowed, it is required — the round cannot close without something concrete to approve. A candidate must be traceable line-by-line to the owner's own answers, offered as a proposal, and labelled as unapproved until they accept the exact words. Offering 2–3 candidates is fine; asserting one as decided is not.
- **Drafting surface copy** — README sections, doc pages, repo description — waits for the approved hero.
- **Editing any file** waits for the approved spec.

### Phase 0 — Excavate (never start from a blank page)

Search for an already-decided north star BEFORE forming any opinion:

- **the repo itself** (always available, never skip): `docs/**/*north-star*`, `*northstar*`, `*positioning*`, `*reposition*`, ADRs, approved design specs, `openspec/`, plus the README's own current opening;
- **project history**: `git log`/`git log --grep` for positioning commits, and issues/PRs if a forge CLI is present;
- **persistent memory**, if such a tool is available in this session (e.g. `mem_search`, memory index files);
- **session history**, if such a tool is available (e.g. `backscroll search "<repo> north star positioning" --all-projects`).

The last two are opportunistic. When a tool is absent, note it as a coverage limit in the excavation report and continue — a missing tool narrows confidence, it never licenses invention.

Report what you found — declared north star, its status, its date, and whether it contradicts the current README — **always paired with the coverage you actually achieved**. A negative result is reported as "none found across <sources swept>", never as "none exists": an incomplete sweep that declares absence manufactures a blank page, which is exactly the condition that produces invention. If any source was unavailable, the negative is provisional and must be re-checked with the owner in Phase 1.

### Phase 1 — Question round (gates the narrative track)

Elicit from the owner what evidence cannot supply. Ask discrete questions, ONE at a time, and STOP for each answer. Minimum coverage:

1. **Business outcome** — what changes for someone using this, stated as a transformation.
2. **Target audience & trigger** — who, and what makes them need it (complexity, scale, pain).
3. **Scope boundaries** — what this product explicitly is NOT, and what stays out of the hero.
4. **Negative space** — adjacent tech, vendors, standards, or ecosystem partners that must NOT define the category.
5. **Tradeoffs** — what the positioning deliberately sacrifices.

Skip a question only when Phase 0 already answered it with an owner-approved record; name that record. Close the round by restating hero + support line and getting explicit approval of the exact wording. That approved wording is quoted verbatim in the spec.

**On approval, re-enter Phase 2.** List what the approved promise claims, subtract what the earlier sweep already verified, and probe the remainder before anything downstream consumes the gap list. A hero approved after the sweep is the single most likely place for an unverifiable claim to enter — it is new language, written to be attractive, describing behavior nobody has checked in those terms. If the delta is empty, say so explicitly; do not leave it unstated.

**If no owner is reachable** (unattended run, or the request came from an automated trigger), the round cannot close and neither gate can ever be satisfied. The run becomes **report-only**:

- **Do not** answer the questions on the owner's behalf, and do not treat an unapproved candidate as settled.
- **Do** continue into Phase 2 — pains, runtime probe, and ghost sweep need evidence, not an owner — and complete it.
- **Stop before Phase 3.** No spec, no scope split, no slices.
- Deliver the Phase 0 excavation result and the Phase 2 gap list, naming the question round as the blocker.
- **No file edited, no commit, no push, no repo-description change**, including when an already-declared north star makes the drift obvious. An unattended run may describe what should change; it may never change it.
- **The expedited correction path does not apply here.** It skips the *approval* queue, not the unattended-write prohibition — those guard different risks: one is "nobody agreed to this claim", the other is "nobody is watching this run". A report-only run surfaces live falsehoods as its top finding and still writes nothing.

### Phase 2 — Verify pains and runtime truth

- **Pains**: validate the 2–3 recurring pains against real evidence — issues, usage, session history, and where relevant external/community signal. A pain is verified when evidence shows it, not when it sounds plausible.
- **Runtime probe**: exercise the product against the claims it is measured by, including the adversarial case (a "works without X" claim gets executed in an environment without X). The target set depends on how far the run got: with an approved hero, probe what that promise implies; without one — a report-only run, or a round still open — probe the claims the docs **already** make today. The current README is always a valid target, so this step never stalls waiting for a hero. How you exercise it depends on what the repo ships — see the table below.
- **Ghost sweep**: extract every documented *invocable unit* and exercise each. Classify: correct / stale / ghost.
- **Quantifier sweep**: every universal in the copy — *every, only, never, always, all, no* — is a promise about a set nobody enumerated. List them, then settle each one.

The ghost sweep proves a documented unit **exists**; it cannot settle a claim about behaviour or coverage. Those are different failure modes, and the first check passes cleanly while the second is false. Each universal ends in exactly one of three states:

| State | How you get there | What to do |
|---|---|---|
| **Verified** | The domain is finite, so you enumerated all of it and found no counterexample ("`--json` exists on 5 of 10 commands" settles "every command supports `--json`" — as false; enumerating all 10 is what settles it either way). Or the domain is open, so you found the one code path that would violate the claim and showed it cannot be reached. | Ship it, and record what you enumerated or which branch you read — the next round should not redo the work |
| **Falsified** | A counterexample exists | Fix per *a correction inherits the discipline of the claim it replaces*: drop, narrow to what you measured, or state the split. Do not assert the negation |
| **Unverifiable** | The domain is open and you cannot show the violating path is unreachable | The universal does not ship. Narrow it to the case you did check, or cut it |

Sampling settles nothing. Three commands that support a flag do not verify "every command"; one platform that links system libraries does not verify "any binary does".

The invocable unit and its authority differ by artifact type. Identify the type first; a repo may be more than one.

| Artifact type | Invocable unit | Verification authority (in precedence) |
|---|---|---|
| CLI / binary | command + flag | `--help` output → flag definitions in source → tests → real execution (build a local dev binary if it self-updates) |
| Library / SDK | exported symbol + signature | public API surface in source → generated API docs → tests/examples that compile and run |
| Service / API | endpoint + payload shape | route definitions → schema (OpenAPI/proto) → integration tests → a request against a local or disposable instance |
| App / UI | user-facing flow | E2E tests → component source → the app running locally |
| Config / infra | key + effect | schema or parser source → a real consumer of the key in code → an applied run in a throwaway environment |
| Docs-only / content | cross-reference + asset | link and anchor resolution → referenced file existence |

**Verification never mutates shared state.** Read-only inspection first; execution only against local, disposable, or explicitly-designated test environments. Never send requests to a production service, never apply infra config, never run a command that writes to shared data, and never disable a safety check to make a claim verifiable. If the only environment available is production or otherwise shared, stop at the highest read-only level and mark the claim unverified with that reason.

If a documented unit has no safely runnable form in this repo (no build, no fixtures, no isolated environment), say so and downgrade the claim to unverified rather than asserting it. Unverified is a finding; assumed-correct is a defect; verified-by-touching-production is a worse defect than either.

Output a gap list splitting DOC gaps (copy is wrong) from BEHAVIOR gaps (runtime cannot back the promise).

### Phase 3 — Scope split and spec

**Entry condition — the gap list must be both current and complete.**

- **Current**: nothing has moved since the sweep. Re-enter Phase 2 if the hero was approved or changed after it, *or* if the runtime changed under it — including the prerequisite change landing, which is the whole point of that change and therefore guarantees the sweep is out of date. Blocked doc slices resume only after re-verifying the claims the prerequisite was supposed to enable; that it shipped is not evidence that it worked.
- **Complete for what the spec asserts**: every claim the spec states as fact must be verified. A claim that stayed unverified — no safe environment, no runnable form — may be omitted, narrowed to what was verified, or marked in-development, but it may **not** appear as an asserted requirement. Currency is not coverage: a gap list can be perfectly up to date and still carry claims nobody could check.

A spec built on a stale gap list ships a promise nobody verified; one built on an incomplete gap list ships a promise nobody *could* verify.

**If the re-probe kills a claim the approved hero makes**, the hero is what has to change, not the evidence. Return to Phase 1 with the finding, get new wording approved, and treat any spec drafted meanwhile as lapsed — it rested on the old hero. This is the loop the "behavior before narrative" rule implies: the runtime gets the last word on what the promise may say.

Behavior gaps become a prerequisite change with its own cycle; the doc change declares it a blocker, does not implement it, and **names the claims to re-verify once it lands**.

**A behavior gap where the docs already make the claim is a live falsehood, not a queued improvement.** The prerequisite blocks *adding* the promise; it does not make a disproven published claim wait out an engineering cycle. Correct that claim on the expedited path and let the full promise land after the behavior does.

Then write the change spec:

- **Purpose** — one line: a truthful, outcome-led doc contract, without changing product behavior.
- **Requirements** — `MUST` / `MUST NOT` statements, each with a `GIVEN / WHEN / THEN` scenario. Cover at minimum: lead with the approved outcome (verbatim), the audience frame, the value hierarchy, consumers vs category, optional context kept out of the core narrative, progressive verified proof, and every technical claim bounded.
- **Surface inventory** — every file to touch, with why.
- **Slices** — each preserving the full message hierarchy, independently reviewable and shippable.

### Phase 4 — Deliver

Apply per slice. Align satellites: repo description = hero; badge ⇄ LICENSE ⇄ README ⇄ agent skills tell one story. Re-run the ghost sweep after edits. Report findings to screen before applying fixes; commit conventionally, version-agnostic.

**If the spec lapses mid-delivery** — a slice disproves a claim, or an input moves while slices remain — stop at the current slice boundary and sort the shipped work into two piles, because they get opposite treatment:

- **Shipped text a slice proved false.** Correct it first, on the expedited path below — it is live, and readers are being misled now.
- **Everything else already applied stays**, including claims that merely became *unverified*. It was approved, delivered, and nothing has disproven it; reverting sound work to tidy the process loses more than it fixes.

Then report what shipped, what was corrected, what remains, and what lapsed the approval — and re-approve the revised spec before touching the remaining slices. Never carry a lapsed approval across a slice boundary on the argument that the change is small.

## Output Contract

A full run returns all seven items, in this order. A **report-only run returns items 1–4 only**, plus a closing line naming the question round as the blocker and listing which behavior gaps would become a prerequisite change; items 5–7 are Phase 3 artifacts and must be omitted, not sketched.

1. **Excavation result** — north star found (source, date, status), or none found across the sources swept, with any unavailable source named.
2. **Approved hero + support line**, verbatim as the owner accepted them, with the approval noted. On a report-only run, state instead that the hero is unapproved and the question round is the blocker — never fill this slot with a candidate presented as settled.
3. **Verified pains** with their evidence.
4. **Gap list** split DOC vs BEHAVIOR, each with `file:line` vs command/source evidence, and the claim set it was probed against — including the post-approval delta, or an explicit statement that the delta was empty.
5. **Prerequisite change** (if any) and what it blocks.
6. **Change spec** — requirements with scenarios, surface inventory, slices.
7. **Historical records left untouched**, listed deliberately.

## References

- `references/method.md` — full method: excavation, the question round, pain validation, verification procedure, spec shape, agent-instruction sync, truth mechanics, and worked case studies.
