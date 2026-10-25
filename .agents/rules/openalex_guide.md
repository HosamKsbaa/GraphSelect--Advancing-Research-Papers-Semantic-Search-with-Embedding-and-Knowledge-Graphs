# OpenAlex reference guide

Checked against the official OpenAlex documentation on 2026-10-09. Implemented in `code/engines/openalex/`.

## Lookups and discovery

- Use `GET /works?search.title=<title>&per_page=10` for title candidates. Provider relevance is not an ALRS research-question similarity score.
- Normalize the selected DOI and resolve it through `GET /works/doi:<doi>`.
- Read `referenced_works` from the seed, then batch-fetch those IDs using `GET /works?filter=openalex:W1|W2&per_page=100`.
- Filter commas mean AND; pipes mean OR within one filter. OpenAlex accepts up to 100 OR values; ALRS requests at most 50 IDs per batch.
- Resolve named authors, venues, and institutions to their typed OpenAlex IDs before using relationship filters. Do not substitute a free-text name for an entity ID.
- Singleton lookups can redirect after an ID merge. Follow only same-origin redirects and count each HTTP request against the run budget.

## Authentication and rate limits

- Inject one application-owned `httpx.AsyncClient`; do not create network clients during module import.
- Send credentials through `Authorization: Bearer <key>`. Never place credentials in receipts, error messages, or request URLs.
- Current basic anonymous queries are supported. Older references to a separate polite pool must not be treated as the current authentication contract.
- Provide an identifying User-Agent and an optional configured contact email. Apply the shared rate limiter, request budget, active-time budget, and at most two retries for throttling/transient failures.
- The ALRS default is five provider requests including retries and 30 seconds of active execution. Persist an attempt before making its HTTP request.

## Record handling

- Keep the provider ID and raw available metadata in provenance. Missing DOI records are explicitly omitted from `Paper` ingestion; never invent a DOI or place an OpenAlex ID in the DOI field.
- Preserve missing abstracts and unknown retraction status. The absence of an OpenAlex retraction flag is not a verified clean bill of health.
- Normalize DOI casing and prefixes before deduplication. Return partial coverage when records are omitted, unavailable, or budget-limited.

## Official references

- [Authentication](https://help.openalex.org/api/authentication/)
- [Search parameters](https://help.openalex.org/api/searching/)
- [Singleton lookup and merged IDs](https://help.openalex.org/api/get-single-entities/)
- [Filters](https://help.openalex.org/api/filtering/)
- [Batch and citation recipes](https://help.openalex.org/how-to/api-recipes/)
