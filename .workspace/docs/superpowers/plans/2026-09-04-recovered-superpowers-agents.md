# Recovered Superpowers Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve six exactly recovered Superpowers agent definitions as an inactive, publicly versioned Handbook artifact family.

**Architecture:** Copy verified recovery bytes into `agents/superpowers/`, add portable provenance and family documentation, and link the inactive family from the root README. Do not register, install, adapt, or activate any agent.

**Tech Stack:** Markdown, JSON, Python standard library verification, Git, Rootline, GitHub pull requests.

**Spec:** `.workspace/docs/superpowers/specs/2026-09-04-recovered-superpowers-agents-design.md`

## Global Constraints

- The six `.md` files must match the byte counts and SHA-256 values in the spec exactly.
- Do not normalize, edit, modernize, rename, combine, install, register, link, map, or activate them.
- Add no package manifest, runtime setting, installer, symlink, alias, test, or CI behavior.
- Public provenance must contain no user name, home path, session path, database path, or host identifier.
- Handbook owns the files and publishes them under its MIT License.
- Existing complete repository validation remains mandatory before commit.

---

### Task 1: Preserve the recovered agent family

**Files:**
- Create: `agents/README.md`
- Create: `agents/superpowers/provenance.json`
- Create: `agents/superpowers/superpowers-architecture-reviewer.md`
- Create: `agents/superpowers/superpowers-debugger.md`
- Create: `agents/superpowers/superpowers-final-reviewer.md`
- Create: `agents/superpowers/superpowers-integration-worker.md`
- Create: `agents/superpowers/superpowers-mechanical-implementer.md`
- Create: `agents/superpowers/superpowers-task-reviewer.md`
- Modify: `README.md`
- Test: none, by explicit owner decision

**Interfaces:**
- Consumes: private recovery bundle with manifest SHA-256 `81969a587f52d4b03d1c5835fe48816d4336c1b03be429f848af5fcfdbde724d`.
- Produces: an inactive `agents/` family matching the approved spec.

- [ ] **Step 1: Verify the recovery source and active config preimage**

Verify the bundle manifest hash above, its `inactive-recovery-bundle` status, `activation: none`, and six-file inventory. Record SHA-256 preimages for `~/.pi/agent/settings.json` and `~/.pi/agent/extensions/subagent/config.json`; stop if either path is missing.

- [ ] **Step 2: Copy the definitions exactly**

Copy only `agents/superpowers-*.md` from the verified private bundle into `agents/superpowers/`. Do not route the copies through an editor or formatter.

- [ ] **Step 3: Add portable documentation and provenance**

Create `provenance.json` with schema `handbook/recovered-agent-provenance/v1`, status `inactive`, owner `pablontiv/handbook`, license `MIT`, the capture/deletion timestamps from the spec, the portable recovery method, and exactly the six filename/byte/hash records from the spec.

Create `agents/README.md` explaining purpose, ownership, MIT licensing, hash verification, inactive status, Pi-oriented tools, and the `mem_save` compatibility boundary. Add `agents/` to the root README inventory and one concise capability entry. Do not document installation instructions.

- [ ] **Step 4: Verify the preservation boundary**

Check all six published files byte-for-byte against the private bundle. Recompute their byte counts and hashes against the spec and provenance. Parse the JSON, scan `agents/` for private absolute paths, and confirm the two active config hashes are unchanged. Confirm no recovered agent exists in an active Pi agent directory.

Validate ADR 0028, the spec, and this plan with Rootline; run `git diff --check`, diagnostics, and every existing local command represented by `.github/workflows/ci.yml` and `.github/workflows/test-model-optimizer.yml` using the normal Homebrew `python3`, not a login-shell Python 3.9. Inspect the complete diff for any activation surface.

- [ ] **Step 5: Commit**

Stage only `agents/`, `README.md`, and this plan. Verify the staged path set and commit as:

```bash
git commit -m "docs(agents): preserve recovered Superpowers roles"
```

---

### Task 2: Review and deliver

**Files:**
- Review: `origin/main..HEAD`
- External effect: push branch, create pull request, observe CI, merge
- Test: no new tests; use Task 1 evidence and independent read-only review

**Interfaces:**
- Consumes: clean preservation branch containing ADR 0028, approved spec, plan, exact definitions, provenance, and docs.
- Produces: merged inactive `agents/` family on `origin/main`.

- [ ] **Step 1: Obtain independent review**

Review `origin/main..HEAD` for exact hashes, portable provenance, truthful inactive documentation, MIT ownership, governed-record validity, clean worktree, and absence of package/runtime/settings/symlink/installer/test/CI changes. Critical or Important findings block delivery until fixed and re-reviewed.

- [ ] **Step 2: Publish the pull request**

Fetch and verify `origin/main`. If it differs from the reviewed base, integrate the new authority and repeat verification. Push `docs/recover-superpowers-agents` and create one PR against `main`. List ADR 0028, disclose inactive status and the explicit no-new-tests decision, and include complete existing-suite evidence.

- [ ] **Step 3: Merge and verify**

Require successful PR checks, a reviewed head matching the PR head, and mergeable state. Merge through the PR without force or direct main delivery. Verify the merge commit on `origin/main` and successful post-merge workflows.

- [ ] **Step 4: Notify dependent sessions**

Send the verified merge commit to sessions waiting on ADR numbering or README changes. They must refresh `origin/main` before generating ADRs or editing README.
