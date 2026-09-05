# GitHub Security Hardening Design

## Goal

Keep `pablontiv/handbook` publicly readable while making `pablontiv` the only human actor who can propose repository changes, write branches, or merge into `main`. Permit Dependabot as the sole automated change proposer. Harden branch delivery, GitHub Actions, dependency maintenance, code scanning, secret detection, vulnerability reporting, and release integrity without treating configuration completion as proof that the controls work.

## Verified starting state

Read-only observations on 2026-09-04 established that:

- `pablontiv/handbook` is already public and owned by `pablontiv`;
- `pablontiv` is the only direct collaborator and has admin permission;
- pull-request creation is already restricted to collaborators;
- no pending invitations, deploy keys, webhooks, repository rulesets, branch protection, or user-installed GitHub Apps can write to the repository;
- GitHub Actions is enabled for all actions, with a read-only workflow token and no permission to approve pull requests;
- secret scanning and push protection are enabled;
- Dependabot alerts, Dependabot security updates, private vulnerability reporting, and CodeQL default setup are disabled;
- immutable releases are enabled;
- the current `main` commit is verified and the nine current GitHub Actions checks pass;
- one draft pull request exists and is authored by `pablontiv`.

These observations are evidence for the initial state only. Every live mutation must be followed by a fresh read.

## Actor and contribution model

`pablontiv` is the only authorized human contributor. No other person receives collaborator, team, deploy-key, app, or invitation-based write access.

Dependabot is the only approved non-human proposer. It may open pull requests for security and version updates but may not merge them. GitHub Actions may execute checks with a read-only token and may not approve pull requests. CodeQL and AI findings may report findings but may not write fixes or consume AI credits through agentic remediation without a separate authorization.

Public forks remain possible because GitHub does not expose a forking prohibition for this public personal repository. Fork owners cannot open pull requests against the upstream repository while `pull_request_creation_policy` remains `collaborators_only`.

## Pull requests and `main`

The repository remains public, pull requests remain enabled, and pull-request creation remains `collaborators_only`.

Classic branch protection on `main` will:

- require changes to arrive through a pull request;
- apply to administrators, with no bypass actor configured;
- require the branch to be current before merge;
- require the nine observed GitHub Actions checks, each bound to the GitHub Actions app identity reread immediately before mutation;
- require signed commits, linear history, and resolved review conversations;
- reject force pushes and branch deletion;
- require zero GitHub approvals.

Zero approvals is intentional. GitHub counts required approvals from actors with repository permissions, so requiring one would make the sole collaborator unable to merge their own pull request. Independent review remains a workspace delivery gate and must be evidenced outside an impossible GitHub approval requirement.

Only squash merge remains enabled. Merge commits and rebase merge are disabled, auto-merge remains disabled, merged branches are deleted automatically, and web-created commits require signoff.

## GitHub Actions

Actions remains enabled but changes from `all` to `selected`:

- GitHub-owned actions and reusable workflows are allowed;
- Marketplace actions from verified or arbitrary publishers are not allowed;
- every action reference must use a full commit SHA;
- the default workflow token remains read-only;
- workflows remain unable to approve pull requests;
- workflows from external fork contributors require owner approval as defense in depth, even though external pull-request creation is blocked.

The repository's current workflows already use GitHub-owned actions pinned to full SHAs, so this policy should not invalidate the observed CI definition.

## Dependency maintenance

Add `.github/dependabot.yml` with version 2 syntax. It covers exactly the ecosystems observed in the repository:

- `pip` at `/`;
- `github-actions` at `/`.

Both run weekly. Version updates are grouped by ecosystem to bound PR volume. Dependabot alerts, security updates, and grouped security updates are enabled in GitHub. Dependabot may propose changes, but all branch protection and CI requirements apply before `pablontiv` can merge them.

No unobserved ecosystem or directory is invented. Adding a new package ecosystem later requires updating the versioned configuration and its contract test.

## Security analysis and disclosure

Enable the following controls where the live repository reports them as supported:

- dependency graph and vulnerability alerts;
- Dependabot security updates and grouped security updates;
- private vulnerability reporting;
- secret scanning and push protection, preserving their enabled state;
- non-provider secret patterns;
- secret validity checks;
- CodeQL default setup with the `extended` query suite;
- AI findings preview.

Copilot Autofix remains available in its current state, but no agentic fix is executed and no AI Credits are authorized by this design.

CodeQL is not added to branch protection before it produces an observed check on the repository. After its first completed run, the exact successful check names and app identity are presented in a second digest-bound mutation manifest. AI findings remain advisory and are not treated as a deterministic merge gate.

Immutable releases remains enabled. Existing release state is not rewritten.

## Durable artifacts

This change owns:

- this design specification;
- an accepted ADR describing the security posture and rejected alternatives;
- an implementation plan;
- `.github/dependabot.yml`;
- a contract test for the Dependabot configuration.

The design does not store credentials, GitHub tokens, personal absolute paths, or mutable API responses.

## Delivery and live rollout

Repository changes occur in a dedicated worktree and are delivered through a pull request. The complete local test suite and Rootline validations run before commit and again before delivery.

Live GitHub mutations occur only after the versioned configuration is merged. Before the first mutation, the executor renders one canonical JSON manifest containing every HTTP method, endpoint, and request body, computes its SHA-256 digest, and requests explicit approval tied to that digest. A changed byte requires new approval.

The rollout is staged:

1. verify repository identity, visibility, owner, revision, collaborators, invitations, keys, apps, and current settings;
2. apply access-preserving repository, Actions, dependency, disclosure, secret, and CodeQL settings;
3. reread each setting and observe the initial CodeQL execution;
4. render and approve a second manifest for the exact CodeQL check gate;
5. apply final branch protection and reread it;
6. report each acceptance criterion as `passed`, `failed`, `unknown`, or `not_applicable`.

A live request failure stops the rollout. There is no automatic retry, substitute endpoint, or inferred success. Diagnosis, review, and renewed authorization are required before another mutating request.

## Verification

Local verification must demonstrate:

- `.github/dependabot.yml` parses as YAML;
- its version is `2`;
- it contains only `pip` and `github-actions` at `/`;
- both schedules are weekly and grouped;
- the existing complete repository suite passes;
- Rootline validates all governed Markdown.

Remote verification must demonstrate:

- visibility remains public;
- `pablontiv` remains the only human with repository access;
- pull-request creation remains collaborators-only;
- Dependabot is the only approved automated proposer;
- `main` protection has no bypass and enforces the approved requirements;
- Actions permits only GitHub-owned, full-SHA-pinned dependencies with a read-only token;
- each approved security feature reports enabled;
- CodeQL has completed successfully before its check becomes required;
- no unapproved external actor, app, key, invitation, or webhook gained write capability.

## Non-goals

This design does not prevent public cloning or forks, authorize other human collaborators, disable Issues or Wiki, create organization-level policy, spend AI Credits on remediation, merge the implementation pull request without a separate human gate, or treat a successful API response as sufficient verification.
