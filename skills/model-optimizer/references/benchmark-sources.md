# Benchmark source registry

Benchmarks are priors for shortlisting and interpretation. They never establish runtime availability, never replace live checks, and never by themselves justify `CHANGE` for an opaque alias or `FAMILY_PROXY` route.

Query only sources relevant to the affected role. Do not sweep this registry on every run. For every observation captured through `cache-benchmark`, record source URL, retrieval time, source or harness version, evaluated checkpoint/provider/effort identity, metric, observation date, and identity match class. A failed search or unavailable site is `SOURCE_UNAVAILABLE`, never proof of `ABSENT`.

## Identity classes

- `EXACT`: same checkpoint/provider route and same effort or explicitly compatible no-effort harness.
- `MODEL_EQUIVALENT`: same model checkpoint through another serving route with enough public evidence to prove equivalence.
- `FAMILY_PROXY`: related family or variant only; useful as weak prior, never exact credit.
- `ABSENT`: exact identity was not found after the bounded relevant source set was successfully queried.
- `UNKNOWN`: opaque provider alias, undisclosed checkpoint, or insufficient identity metadata.
- `SOURCE_UNAVAILABLE`: source could not be queried, rendered, authenticated for public access, or verified within the bounded run.

## Approved sources

| Source | Role relevance | Identity requirement | Harness requirement | Effort requirement | Date/retrieval requirement | Availability requirement |
| --- | --- | --- | --- | --- | --- | --- |
| Terminal-Bench latest stable | terminal/tool-using coding, shell-oriented debugging, agentic execution | Preserve the exact evaluated model/checkpoint/provider named by the official result; do not transfer to aliases | Record Terminal-Bench harness/version shown by the source | Record the evaluated effort/reasoning mode when published; otherwise `omit` | Record source result date plus current retrieval timestamp | Public official result/leaderboard page must load and identify the stable version; otherwise `SOURCE_UNAVAILABLE` |
| Terminal-Bench 2.1 | terminal/tool-using coding and shell repair where version 2.1 is specifically cited | Treat 2.1 results as Terminal-Bench 2.1 only; do not generalize to latest stable or 3 | Record Terminal-Bench 2.1 harness/version exactly | Record effort/reasoning exactly as listed or `omit` | Record result date and retrieval timestamp | Public Terminal-Bench 2.1 result must be reachable; failed lookup is `SOURCE_UNAVAILABLE` |
| Terminal-Bench 3 | terminal/tool-using coding and shell repair where version 3 is specifically cited | Treat 3 results as Terminal-Bench 3 only; do not back-port to 2.1 or latest stable | Record Terminal-Bench 3 harness/version exactly | Record effort/reasoning exactly as listed or `omit` | Record result date and retrieval timestamp | Public Terminal-Bench 3 result must be reachable; failed lookup is `SOURCE_UNAVAILABLE` |
| SWE-bench Pro | repository-scale software engineering, integration, bug fixing | Exact evaluated checkpoint/provider preferred; aliases remain `UNKNOWN` or `FAMILY_PROXY` | Record SWE-bench Pro harness/agent/version | Record effort/reasoning mode if the leaderboard discloses it | Record leaderboard date and retrieval timestamp | Public comparable result must be available; otherwise local eval continues with `SOURCE_UNAVAILABLE` |
| SWE-bench Verified Bash Only | code repair where shell-only execution is comparable to the role fixture | Exact model identity required for strong prior | Record Verified Bash Only harness and bash-only constraint | Record effort/reasoning when disclosed | Record observation date and retrieval timestamp | Public source must identify the bash-only subset; otherwise `SOURCE_UNAVAILABLE` |
| Aider Polyglot | multi-language code editing and patch generation | Exact checkpoint/provider where possible; family-only rows are `FAMILY_PROXY` | Record Aider Polyglot version and mode | Record edit format/effort/reasoning if published | Record leaderboard date and retrieval timestamp | Public comparable leaderboard row required |
| METR Time Horizon | long-horizon autonomy, planning, and sustained debugging | Exact model/checkpoint where disclosed; undisclosed serving aliases are `UNKNOWN` | Record METR task family/harness/version | Record reasoning mode/agent scaffold if disclosed | Record publication date and retrieval timestamp | Public result page or report must be reachable |
| SWE-bench Multilingual and Multimodal | multilingual or vision-capable software engineering roles | Exact model and modality support must match role needs | Record multilingual/multimodal harness variant | Record effort/reasoning/modality settings | Record result date and retrieval timestamp | Public comparable subset required; unavailable subset is `SOURCE_UNAVAILABLE` |
| ProgramBench | algorithmic/programming problem solving and mechanical implementation | Exact checkpoint/provider preferred | Record ProgramBench harness/version | Record effort/reasoning if available | Record result date and retrieval timestamp | Public comparable result required |
| LiveBench | general live capability prior, especially reasoning/coding drift checks | Exact model/checkpoint and date-sensitive row required | Record LiveBench version/category | Record effort/reasoning where disclosed | Record benchmark date and retrieval timestamp because LiveBench changes over time | Public current row must be reachable |
| CodeClash | competitive coding only when a comparable public leaderboard is available | Exact evaluated identity required for strong prior | Record CodeClash ruleset/harness and comparable track | Record effort/reasoning if disclosed | Record result date and retrieval timestamp | If no comparable public leaderboard is available, record `SOURCE_UNAVAILABLE` rather than `ABSENT` |
| Artificial Analysis | independently run secondary source for latency, price, and broad capability context | Exact provider/model row needed for operational priors; family rows are `FAMILY_PROXY` | Record Artificial Analysis benchmark/metric page and version if shown | Record effort/reasoning if disclosed; otherwise `omit` | Record retrieval timestamp and page date/version when visible | Secondary prior only; source outage is `SOURCE_UNAVAILABLE` |

## Source URLs

Use HTTPS URLs from the official source pages at retrieval time. Store the exact result URL used for the observation, not a generic search query. If a URL contains a token or tracking query, the helper sanitizes stored URLs; never paste secrets or private dashboard URLs into benchmark evidence.

Common public landing pages to start bounded lookup from:

- Terminal-Bench: `https://www.tbench.ai/`
- SWE-bench: `https://www.swebench.com/`
- Aider leaderboard: `https://aider.chat/docs/leaderboards/`
- METR: `https://metr.org/`
- ProgramBench: official public project or paper leaderboard page available at retrieval time
- LiveBench: `https://livebench.ai/`
- CodeClash: official comparable public leaderboard when available
- Artificial Analysis: `https://artificialanalysis.ai/`

## Bounded use

1. Select sources by archetype, e.g. Terminal-Bench/SWE-bench for integration/debugger, Aider Polyglot for edit-heavy polyglot roles, METR for long-horizon architecture/research, Artificial Analysis for operational priors.
2. Record unavailable sources explicitly as `SOURCE_UNAVAILABLE` for the bounded source set.
3. Never rewrite `SOURCE_UNAVAILABLE` to `ABSENT` later without a successful bounded query.
4. Never allow `FAMILY_PROXY` or `UNKNOWN` benchmark-only evidence to produce `CHANGE`.
5. Require runtime-exact local evidence for every final assignment.
