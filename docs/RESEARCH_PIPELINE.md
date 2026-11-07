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

## Current limitations

There is no autonomous daily scheduler or automatic task creation yet.
The current endpoints are owner-initiated. The next milestone is to let the
CEO synthesize only owner-accepted sources into proposed tasks, with every
task proposal requiring owner review before execution.
