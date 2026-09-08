# Mission Control Attention Panel Design

**Date:** 2026-09-08

**Status:** Approved design; normative for Mission Control presentation, no runtime change

**Governing ADR:** ADR 0032

## Purpose

State what Mission Control owes the Operator on its attention panel, using only the session todos it already keeps, so that routine transport and status traffic stops competing with real decisions in chat.

## Boundary

Mission Control owns presentation. Project Orchestrators retain ownership of their work and its outcomes, and keep emitting the single per-cycle `MISSION_EVENT` line defined by the mission event line design record. Mission Control still relays that line unchanged, as ADR 0031 requires, and additionally reflects it in the matching todo. This record is not one of the roadmap iterations 37 to 41. Nothing here adds a pane, renderer, polling loop, schema, database, or tool.

## Panel content

The panel is the existing session todo list. It tracks three kinds of entry:

- confirmed accomplishments;
- work Mission Control follows;
- decisions pending from the Operator.

Each entry carries: project, owner, last confirmed state, evidence, next event.

## Update rules

- A routine transport or status notification updates the matching todo. It does not produce another chat message.
- One todo per followed work item or pending decision. No todo per log event, and no mirror of a Factory's implementation backlog.
- Chat is reserved for actual decisions, real blockers, and final results the Operator explicitly requested.
- A transport acknowledgement that a line was sent (`SENT`) is not task completion. A pending result is not an Operator decision.

## Canonical Mission Control binding

Harness Pi, model `gpt-6-astra`, thinking `medium`. Changeable only by an explicit Operator override. The provider or account route is not part of this record. This record does not switch the live Mission Control session or any Factory role model.

## Deferred

Any ticker pane, renderer, polling loop, schema, database, or new tool; roadmap issue 38 and later; adoption by other Factories.
