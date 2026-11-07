# Company Knowledge Store

The knowledge store is a persistent runtime database feature. It does not place
company research, private customer data, or strategy records in the public Git
repository.

## Evidence lifecycle

1. Create a candidate with a title, factual note, category, source URL, source
   title, optional publication date, confidence estimate, and tags.
2. The system records when the source was entered and who entered it.
3. Every new item starts with `status=candidate`.
4. An owner-authenticated reviewer can accept or reject a candidate once, with
   an optional review note.
5. Accepted and rejected records are immutable through this API; a new
   correction should be recorded as a new candidate with its own provenance.

The API never fetches or verifies the source URL. A source link is provenance,
not proof that the claim is true. Confidence is an explicitly supplied estimate,
not a calibrated probability. Reviewers must inspect the source independently
before accepting a claim.

## API

- `POST /knowledge` — create a candidate.
- `GET /knowledge?status=candidate&category=market_research&limit=100` — list
  candidates or reviewed records.
- `GET /knowledge/{item_id}` — retrieve one record.
- `POST /knowledge/{item_id}/review` — accept or reject a candidate.

All endpoints are protected by the existing owner authentication middleware.
The dashboard shell being public does not make these data endpoints public.
The audit log records candidate creation and review decisions.

## Current limitations

- No autonomous web crawler or browser is connected.
- Specialist agents may propose up to five knowledge candidates from a model
  report. Candidates are stored as `candidate` and never auto-accepted.
- A candidate is stored only when its exact source URL already appears in the
  supplied task or accepted-reference context. This reduces invented-link risk
  but does not prove the URL or claim is genuine; an owner must inspect it.
- Agents retrieve up to five keyword-matched, owner-accepted notes. Candidate
  and rejected records are excluded. Retrieved text is bounded and marked as
  untrusted reference data in the prompt.
- Retrieval removes exact duplicates by normalized source URL, title, and
  content. When otherwise-relevant records compete, publication-date freshness
  is a tie-breaker; undated sources receive a neutral value. The returned
  retrieval metadata labels this as a heuristic, not source verification.
- Retrieval remains lexical, not semantic. No embeddings or external calls are
  used. Source fetching and verification are not implemented.
- The SQLite database is local runtime state and needs a backup/restore plan
  before production use.
