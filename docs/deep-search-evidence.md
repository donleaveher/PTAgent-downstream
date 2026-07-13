# Deep-Search Evidence Contract

This document records the evidence closure contract implemented for the
downstream experiment pipeline.

## Scope

The pipeline persists each deep-search evidence record, links verdict events to
the evidence rows used, includes them in frozen experiment snapshots, and
renders verdict-specific references from the frozen manifest.

## Non-Goals

- Storing full paper text.
- Re-querying live sources while rendering a frozen report.
- Inferring support or refutation from a title, abstract, or keyword match.

## Evidence Record

Each `DeepSearchEvidence` row belongs to one `experiment_id` and one
`annotation_id`. It stores:

- The verdict stance: `support`, `refute`, or `neutral`.
- Citation title and stable reference (for example, PMID, DOI, or URL).
- The evidence source and its version.
- A short source snippet, normalized query, source provenance, and retrieval time.

The application derives `evidence_id` deterministically from the annotation,
query, source/version, stance, citation content, and provenance. Repeating the same
search therefore reuses the existing evidence row rather than replacing its original
retrieval timestamp. A changed query, source version, citation, stance, or provenance
creates a new row.

The MySQL table is `deep_search_evidence`. It is created additively by
`MySQLExperimentStore.initialize_schema()`; existing experiment data requires no
backfill.

## Verdict Linkage

`AnnotationHistory` remains the append-only verdict ledger. For deep-search
events, `evidence_ref.evidence_ids` contains the stable IDs of the exact evidence
rows used in the verdict. The existing `support_refs` and `refute_refs`
remain for compatibility with older snapshots.

The verdict state machine is unchanged:

- Support only promotes a hypothesis to `CONCLUSION`.
- Refutation only changes it to `REFUTED`.
- Conflicting or insufficient evidence retains `HYPOTHESIS` with a history event.

## Freeze And Report

`freeze_experiment` copies all evidence rows into the snapshot manifest and adds:

- `counts.deep_search_evidence`
- `deep_search.evidence_by_stance`
- `deep_search.verdicts`

The layered report only reads that manifest. It renders source citations beside supported
conclusions, refuted items, and conflicting unresolved items, then includes
`8. Deep-search 证据明细（冻结快照）` with the evidence rows and snippets. Later changes
to live evidence cannot alter a report for an already frozen snapshot.

`pipeline_status` exposes the current live evidence count as
`deep_search_evidence`, which is useful for checking a smoke-test run before
inspecting the frozen snapshot.

## Fixture MySQL Smoke

The fixture smoke uses real MySQL while keeping the literature source local and
deterministic:

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke/deep_search_fixture_mysql_smoke.py
```

It covers support, refutation, conflict, and insufficient evidence; it prints the
persisted evidence IDs, verdict-history links, frozen evidence counts, and report
section check. The fixture records are test data, not scientific conclusions.

## Real PubMed MCP Source

The default production source is `PubMedLiteratureSearchSource`, which connects
directly to PTAgent's local `pubmed-mcp` service at `http://127.0.0.1:3010/mcp`.
It is a downstream dependency and has no relationship to the upstream proteomics
pipeline. The pinned server source is `cyanheads/pubmed-mcp-server` `v2.9.8`,
placed under the ignored `data/runtime/pubmed-mcp-server` directory by
`scripts/setup-pubmed-mcp.sh`.

Each task is processed in two calls: `pubmed_search_articles` receives a Boolean
`(gene) AND (disease) AND (organism)` query and returns PMIDs; then
`pubmed_fetch_articles` retrieves each article's title, abstract, publication type,
and MeSH terms. Every persisted record is deliberately `neutral`. Retrieval does
not infer support or refutation from a title, abstract, or keyword match. The exact
PubMed query, tools, PMID, DOI, PMC ID, journal, MeSH terms, and PubMed URL are
stored in provenance.

When that original-protein query returns zero records, the adapter can fall back to the
ranked candidate-neighbor genes recorded in the hypothesis derivation. Each fallback
uses `(candidate gene) AND (disease)` without the original protein's organism filter,
because the neighbor may be cross-species. These records remain `neutral` and carry
`query_scope=candidate_fallback`, `candidate_gene`, and `primary_query` in provenance;
they are supplementary evidence for the transfer path, not direct evidence for the
original protein. The fallback tries at most
`PTAGENT_DEEP_SEARCH__CANDIDATE_FALLBACK_MAX_QUERIES` candidates (default `3`; `0`
disables it). A non-empty primary result never triggers candidate fallback.

The source retries transient tool failures according to
`PTAGENT_DEEP_SEARCH__MAX_ATTEMPTS` and enforces
`PTAGENT_DEEP_SEARCH__TIMEOUT_SECONDS` per call. A malformed non-empty response or
a fetch with no articles after a non-empty PMID search stops the step instead of
creating partial evidence.

Prepare the pinned service, then start it manually:

```bash
./scripts/setup-pubmed-mcp.sh
docker compose up -d --build pubmed-mcp
```

First validate the local MCP protocol and its real PubMed search-to-fetch path. This
does not use the PTAgent adapter or write MySQL:

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke/pubmed_mcp_smoke.py
```

Then validate the PTAgent adapter using the same no-write retrieval path:

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke/deep_search_mcp_smoke.py
```

## Persisted Real PubMed Smoke

To validate the full durable path with live PubMed records, run:

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke/real_pubmed_mysql_smoke.py
```

This creates a timestamped `exp_real_pubmed_smoke_*` test experiment for the default
`STAT3 × Lupus Nephritis` query. It writes real retrieved records, their verdict
history, a frozen snapshot, and a report to MySQL. The records remain `neutral` by
design, so the test preserves its hypothesis as `insufficient`; it does not claim a
biological conclusion. Use a real experiment identifier only after reviewing the
target hypothesis and accepting the resulting evidence writes.

Set `PTAGENT_DEEP_SEARCH__PROVIDER=generic_mcp` only when intentionally using a
different compatible literature MCP. In that mode the generic adapter still supports
custom tool and argument names.
