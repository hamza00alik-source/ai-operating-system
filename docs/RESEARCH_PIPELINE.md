# Research pipeline

## Free release-feed collection

`POST /research/feeds` searches a fixed allowlist of six public GitHub Atom
release feeds for relevant release notes. It does not require an API key or a
paid search provider. It is manually initiated by the owner, not scheduled or
run at application startup. It makes at most six requests, each with a
12-second timeout and one-megabyte response limit; redirects are rejected.
Only HTTPS GitHub release links are retained. XML DTD/entity declarations
are rejected, and results are limited to 30 candidates per request.

The feed scan is not general-purpose web search. It covers releases from
LangGraph, CrewAI, Prefect, FastAPI, WooCommerce and WordPress. It may miss
relevant announcements outside those feeds and may return no results if a
source is unavailable. Query matching is lexical, not semantic.

All matches are saved as unreviewed knowledge candidates. Feed content is
untrusted data: it cannot issue instructions, create tasks, modify code, or
trigger business actions. Owners review candidates in the dashboard.
Existing source URLs are deduplicated across the knowledge library.

## Optional metered Exa search

The Exa adapter remains separate, disabled by default, and requires both
`AI_OS_RESEARCH_ENABLED=true` and a private `EXA_API_KEY`. It is not called
by the free feed endpoint and no fallback or automatic paid search occurs.

## CEO research-to-task proposals

The owner may invoke `POST /research/task-proposals/draft` when a model provider
has been explicitly configured and enabled. The CEO receives only owner-accepted
company-scope knowledge items, with source IDs, titles, excerpts and provenance.
The model call may incur provider costs and may transmit those excerpts to the
configured provider; the dashboard warns before the call. Model execution stays
disabled by default.

The CEO may propose up to five internal research, analysis, product-validation,
documentation or engineering tasks. Every cited source ID must belong to the
accepted source set supplied to the model. Proposals are deduplicated and stored
as candidates; the CEO cannot create or queue tasks directly. The owner must
approve a proposal in the dashboard. Approval rechecks that every cited source
is still accepted and atomically creates one queued internal task. Rejection
creates no task. Neither approval nor task creation publishes content, contacts
customers, spends money, or triggers an external action.

The proposal generator treats source content as untrusted data and does not
follow embedded instructions. It cannot propose external actions. Model output
is schema-checked and source-ID checked before storage.

## Current limitations

Research collection and CEO drafting are owner-initiated. There is not yet an
autonomous daily scheduler, a continuously running research agent, semantic
search across the public web, or automatic task execution from these proposals.
The worker and external business integrations remain separate governed stages.
