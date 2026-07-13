# Notes: Neighbor Search Refactor

## Sources

- `docs/READING-GUIDE.md`: pipeline guide still describes hypothesis as running structure search directly.
- `docs/IMPLEMENTATION-CHECKLIST.md`: section 6.3 already frames multi-channel neighbor fusion as the next boundary; pipeline orchestration is still marked pending.
- `src/application/knowledge/hypothesis_generation.py`: currently runs `StructureSearchProvider.search(...)`, persists structure status/run/evidence, reranks structure neighbors, and writes hypotheses.
- `src/application/knowledge/neighbor_fusion.py`: currently orchestrates structure evidence + sequence provider and RRF fusion into `FusedCandidate`.
- `src/application/orchestration/pipeline.py`: current order is `... enrichment -> hypothesis -> kg_projection ...`.
- `pkg.experiment` repository/MySQL already support `StructureSearchRun`, `StructureNeighborEvidence`, and `FusedCandidate`.

## Synthesized Findings

- No schema change is required for this refactor.
- Structure search must be split out of hypothesis generation, but it should not be a special default pipeline step.
- `StructureSearchNeighborProvider` should run the structure provider as a normal neighbor provider, persist structure evidence as a side effect, and emit `NeighborCandidate(channel="structure")`.
- `StructureEvidenceNeighborProvider` remains useful for compatibility/backfill paths that read already persisted `structure_neighbor_evidence`.
- `generate_fused_neighbor_candidates(...)` can remain as compatibility wrapper, but should delegate to `run_neighbor_search(...)`.
- Hypothesis generation can become a pure consumer of `FusedCandidate`: fused target accession -> gene resolver -> CTD disease -> protein-level `HYPOTHESIS`.
- Provider abstraction correction: providers now return `NeighborProviderResult(candidates, runs, evidence, statuses)`; `NeighborSearchService` persists supported evidence row types. Provider instances can be built by registered names such as `structure.foldseek`, `structure.evidence`, and `sequence.kmer`.
- Structure provider move: `StructureSearchNeighborProvider`, `StructureEvidenceNeighborProvider`, and `collect_structure_search_artifacts` now live under `pkg.retrieval.providers.structure`; application layer imports them only for registry/compatibility.
- Sequence provider move: `SequenceNeighborProvider` now lives under `pkg.retrieval.providers.sequence`; `pkg.retrieval` re-exports it for compatibility.
- Persistence adapter move: `ProviderPersistenceAdapter` defines result persistence; `StructureEvidencePersistenceAdapter` now owns structure run/evidence/status writes, so `neighbor_search` no longer imports or checks structure row types.
- Generic evidence schema: added `NeighborSearchRun`, `NeighborEvidence`, and `NeighborEvidenceStatus` with repository/MySQL persistence. `NeighborEvidencePersistenceAdapter` writes every successful provider result to generic tables; structure also keeps legacy structure tables via `StructureEvidencePersistenceAdapter`.

## Verification

- Focused tests: `36 passed, 1 warning`.
- Full suite: `240 passed, 1 skipped, 1 warning`.
- After moving structure search into `neighbor_search` as a provider and adding provider-failure fallback coverage: focused tests `16 passed`; full suite `241 passed, 1 skipped, 1 warning`.
- After moving structure providers into `pkg.retrieval.providers`: focused tests `23 passed`; full suite `245 passed, 1 skipped, 1 warning`.
- After moving sequence provider into `pkg.retrieval.providers`: focused tests `17 passed`; full suite `246 passed, 1 skipped, 1 warning`.
- After decoupling provider persistence adapters: focused tests `19 passed`; full suite `248 passed, 1 skipped, 1 warning`.
- Generic neighbor evidence schema focused tests: `33 passed`.
- After generic neighbor evidence schema: full suite `250 passed, 1 skipped, 1 warning`.

---

# Notes: Deep-Search Evidence Closure

## Current State

- `verify_experiment_hypotheses` constructs a deterministic task, calls an injected literature source, decides a verdict, updates the annotation level, and appends `AnnotationHistory`.
- The current history only stores reference lists and query metadata in `evidence_ref`; there is no immutable row per `EvidenceRecord`.
- `get_literature_search_source` explicitly rejects production use until a real source is implemented. `InMemoryLiteratureSource` is test-only.
- `freeze_experiment` currently serializes annotations and annotation history, but not independent deep-search evidence rows.
- `layered_report` renders verdict reference IDs from annotation history but cannot display titles, snippets, stances, or source provenance from an evidence ledger.

## Target Contract

- A `DeepSearchEvidence` row belongs to one experiment and one hypothesis annotation.
- The row contains a stable source-level reference plus the retrieved evidence metadata.
- `AnnotationHistory.evidence_ref` will carry the evidence row IDs used for that verdict.
- The snapshot manifest will contain all evidence rows plus a verdict summary.
- The report will render only frozen evidence relevant to each conclusion, refutation, or unresolved hypothesis.

## Implemented

- `DeepSearchEvidence` is a deterministic, immutable evidence row keyed by a
  stable hash of the annotation, query, source/version, stance, citation, and
  source provenance.
- `AnnotationHistory.evidence_ref.evidence_ids` links each verdict event to
  exactly the evidence rows used for that decision.
- `freeze_experiment` now includes evidence rows and stance/verdict counts in
  the manifest. `layered_report` uses those rows only; it never reads live
  evidence when rendering a frozen report.
- Focused tests pass: `39 passed`.
- Full suite after updating the report-section contract: `257 passed, 1 skipped,
  1 warning`. The warning is the pre-existing Starlette TestClient deprecation.

---

# Notes: Real Literature MCP Integration

## Findings

- The project already has a production broker client at `pkg.mcp.MCPClient`; it
  normalizes MCP tool results to a dict and exposes synchronous `call_tool`.
- Existing workflow conventions use tool `deepxiv_search` with `query` and
  `top_k`. The external provider remains separately deployed through the broker.
- The generic DeepXiv result schema is not encoded locally. The adapter must normalize common
  result list and paper fields while rejecting malformed non-empty responses.
- Raw literature search results must not be classified from titles or snippets. Only a source
  provided stance is eligible for support/refute; unknown stance is neutral.

## Implemented

- `DeepSearchSettings` configures tool name, query/limit arguments, result limit,
  timeout, retry policy, source version, and the neutral default stance.
- `MCPLiteratureSearchSource` uses the existing broker client, validates result
  records, retries call failures, and stops malformed non-empty output from entering MySQL.
- `scripts/smoke/deep_search_mcp_smoke.py` is a no-write real-MCP smoke.
- Automated verification: focused tests passed and the full suite is
  `263 passed, 1 skipped, 1 warning`. The remaining step is a user-run query
  against the real configured MCP provider.

---

# Notes: Self-Hosted PubMed MCP

## Source And Deployment

- Selected server: `cyanheads/pubmed-mcp-server` pinned at tag `v2.9.8`, commit
  `ef0be2c0cf71164460243834e871391d3632b51d`.
- The checkout lives in ignored `data/runtime/pubmed-mcp-server`; use
  `scripts/setup-pubmed-mcp.sh` to restore the exact tagged source on another machine.
- `docker-compose.yml` defines `pubmed-mcp`, bound only to `127.0.0.1:3010`.
  It is independent from the upstream data-processing pipeline.

## Adapter Contract

- `PubMedLiteratureSearchSource` first calls `pubmed_search_articles`, then calls
  `pubmed_fetch_articles` with the returned PMIDs.
- The task context becomes `(gene) AND (disease) AND (organism)` when these fields
  are present. The supplied task query is retained only as a fallback.
- Persisted evidence is always neutral retrieval evidence. It includes PubMed query,
  tools, PMID/DOI/PMC identifiers, journal, MeSH, type, URL, and abstract snippet.
- `scripts/smoke/pubmed_mcp_smoke.py` is the direct no-write protocol smoke. It checks
  tool registration and performs `pubmed_search_articles` → `pubmed_fetch_articles`
  without involving the PTAgent adapter or MySQL.
- `scripts/smoke/deep_search_mcp_smoke.py` remains the adapter-level no-write smoke;
  run it after the direct MCP smoke succeeds.

## Runtime Verification (2026-07-13)

- The initial Docker Hub timeout was caused by the active Clash node's unstable route,
  not Docker login or the MCP configuration. Switching the Clash node resolved it.
- `docker compose up -d --build pubmed-mcp` built `ptagent-pubmed-mcp:v2.9.8` and
  started the local-only service on `127.0.0.1:3010`.
- A direct protocol smoke should verify tool discovery plus the search → fetch sequence
  independently of PTAgent's deep-search adapter, without writing MySQL or annotations.
- The direct smoke compiles and renders its CLI help successfully. Focused adapter
  regression coverage passes: `14 passed in 0.38s`.
- `scripts/smoke/pubmed_mcp_smoke.py` passed: 10 tools discovered, 3 PMIDs searched,
  and 3 article records fetched.
- `scripts/smoke/deep_search_mcp_smoke.py` passed: the adapter emitted 5 PubMed
  `neutral` evidence records for the structured STAT3/lupus-nephritis query.
- `scripts/smoke/deep_search_fixture_mysql_smoke.py` passed using the local MySQL
  container. It persisted experiment `exp_deep_search_smoke_20260713_044012_665993`,
  four evidence rows and four verdict-history rows; the frozen manifest and report
  evidence section both contained the expected four fixture records.

## Persisted Real PubMed Smoke

- Local MySQL currently contains fixture smoke experiments only; no user-provided
  `HYPOTHESIS` annotation is available to run against PubMed.
- A dedicated `STAT3 × Lupus Nephritis` test experiment will therefore isolate the
  first real retrieval-and-persistence run from user data. The expected outcome is
  persisted neutral evidence and an `insufficient` verdict, not a biological conclusion.
- `scripts/smoke/real_pubmed_mysql_smoke.py` passed on 2026-07-13. It created
  `exp_real_pubmed_smoke_20260713_044423_103466`, retrieved and persisted five real
  PubMed records through `PubMed-MCP`, appended one `insufficient` history event, and
  verified that the frozen snapshot and report retain all five evidence rows.

## Full Downstream Pipeline Smoke

- `scripts/smoke/foldseek_sequence_domain_hypothesis_real_smoke.py --include-deep-search`
  passed on 2026-07-13 for `exp_fs_seq_dom_hyp_smoke_20260713_051913_232984`.
- The successful path was: local AlphaFold model → real Foldseek → local UniProt-derived
  sequence/domain channels → CTD hypothesis → in-memory KG projection → live PubMed
  deep-search → MySQL snapshot and report. It persisted 10 structure, 10 sequence, and
  10 domain evidence rows; generated one JAK1/Lupus Nephritis hypothesis; and wrote five
  neutral PubMed records plus one history event.
- It deliberately did not run production `base_annotation` (no real UniProt MCP) or a
  persistent Neo4j projection (Neo4j is not running); its graph projection used the
  existing `InMemoryGraphStore` smoke implementation.
- Direct MySQL verification confirmed 28 CTD conclusions, one remaining hypothesis,
  five `pubmed-mcp-v2.9.8` evidence rows, one `insufficient` verdict, and a FINAL 1.0
  snapshot/report whose frozen evidence count is five.
- Regression verification after adding the opt-in PubMed stage and hardening failure
  isolation tests: full suite `265 passed, 1 skipped, 1 warning`.

## Candidate-Gene PubMed Fallback

- The full pipeline generated a JAK2/Lupus Nephritis hypothesis through the JAK1
  neighbor (`via_genes=["JAK1"]`) and correctly queried JAK2 to test that transferred
  hypothesis directly.
- The desired extension is not to replace that direct query, but to issue a separately
  labeled candidate-gene fallback query only when the direct query returns zero records.
- Live no-write verification used an intentionally nonexistent primary gene with
  `candidate_genes=("JAK1",)`. The primary PubMed query returned zero results; fallback
  query `(JAK1) AND (Lupus Nephritis)` returned five neutral records, each labeled
  `query_scope=candidate_fallback` with its candidate gene and primary query.

## Persisted Fallback Smoke Verification

- Full pipeline experiment `exp_fs_seq_dom_hyp_smoke_20260713_054533_343607` completed
  with all eight selected stages `ok`, two hypotheses, eight evidence rows, a final
  snapshot, and a report.
- Five evidence rows for the Lupus Nephritis hypothesis were persisted with
  `query_scope=candidate_fallback`, `candidate_gene=JAK1`, the fabricated primary query
  for `PTAGENT_NONEXISTENT_GENE_987654`, and fallback query `(JAK1) AND (Lupus Nephritis)`.
- The other three rows belong to a separate Prostatic Neoplasms hypothesis and used
  `query_scope=primary`; a forced-fallback assertion must therefore select the expected
  fallback subset instead of assuming every evidence row uses fallback.
- The reusable assertion is now opt-in on
  `scripts/smoke/foldseek_sequence_domain_hypothesis_real_smoke.py`:
  `--expect-candidate-fallback` requires `--include-deep-search` and checks the expected
  candidate gene, primary query, fallback query, and exact evidence-ID equality between
  MySQL and the frozen snapshot.
- Live regression run `exp_fs_seq_dom_hyp_smoke_20260713_060234_001623` passed with
  five JAK1/Lupus fallback rows in both places; full Python regression suite afterward:
  `268 passed, 1 skipped, 1 warning`.

## Real Neo4j KG Smoke

- The local Compose definition already provides `neo4j:5-community` as `ptagent-neo4j`
  with browser port 7474 and Bolt port 7687. The user has started it and verified an
  authenticated `cypher-shell` `RETURN 1` query.
- The production double-node graph implementation is already present in
  `pkg.graph.neo4j_store.Neo4jGraphStore`; it creates constraints, uses parameterized
  `UNWIND`/`MERGE`, and implements the same `GraphStore` port exercised by the existing
  in-memory unit tests.
- The next validation should use `project_experiment_kg` with a real MySQL repository and
  real Neo4j store. It must check canonical general facts plus experiment-scoped edges,
  traversal, idempotent re-projection, and cleanup isolation.
- Live smoke `exp_neo4j_smoke_20260713_085804_814273` and its peer passed against
  `bolt://127.0.0.1:7687` / database `neo4j`: each projection had 10 nodes and 8 edges,
  including one structural and one fused-candidate edge. The primary re-projection was
  idempotent; deleting its six workspace artifacts preserved the peer workspace and its
  general conclusion fact. The peer workspace was then removed as cleanup.
- Full Python regression after adding the smoke and runbook: `268 passed, 1 skipped,
  1 warning`. The existing warning is Starlette's `TestClient`/`httpx` deprecation.

## Neo4j Smoke State Output

- The smoke can retrieve two complementary structural states before cleanup: MySQL
  `StructureSearchRun`/`StructureNeighborEvidence` records (provider, status, rank,
  score, coverage, evidence ID) and the Neo4j `STRUCTURAL_NEIGHBOR` edge that carries
  the same lightweight provenance.
- The KG state should show the scoped workspace counts, key nodes, disease traversals,
  structural-neighbor edges, and fused-candidate edges. Full structure files remain in
  external storage and are intentionally not copied into Neo4j.
- The live output for `exp_neo4j_smoke_20260713_090324_316937` confirmed MySQL
  `StructureSearchRun.status=completed` and `StructureNeighborEvidence` rank 1, score
  0.95, coverage 0.8. The projected Neo4j `STRUCTURAL_NEIGHBOR` carries the same
  `run_id`/`evidence_id`/rank/score/coverage. This is a controlled smoke fixture, not a
  Foldseek retrieval result.
- The initial fixture omitted a persisted sequence evidence row and used a different
  target for the fused candidate. It is corrected and revalidated in
  `exp_neo4j_smoke_20260713_091450_798951`: structure and sequence evidence both point
  to `NEOSMOKE_NEIGHBOR_*`, and `CANDIDATE_NEIGHBOR` points to that same target with
  both evidence IDs. Sequence remains MySQL-only at the graph-projection layer.

## Neo4j Production Hardening

- Live audit baseline: 62 GENERAL nodes and 32 GENERAL relationships, all smoke fixture;
  no EXPERIMENT relationships after cleanup; 14 orphan nodes remain.
- Correct dependency order is identity → relation/evidence semantics → atomic replace →
  verdict/query isolation → frozen graph manifest → GNN properties → operations/migration.
- Improvement plan: `docs/neo4j-improvement-plan.md`.
- Phase 1 focused verification: canonical identity + GraphStore + KG projection suites
  passed (`33 passed`). Protein accessions now normalize before projection; Gene keys are
  NCBI-ID-first or taxon-aware normalized symbols while query output keeps readable symbols.
- Neo4j hardening completed on 2026-07-13: stable entity/relation identity, strict fused
  evidence validation, atomic experiment replacement, experiment-isolated traversal,
  schema-v2 graph manifests, deterministic GNN export, Comparison nodes, native properties,
  localhost-only pinned Compose service, healthcheck/timeouts/cleanup, and dry-run rebuild.
- Full regression after all phases: `280 passed, 1 skipped, 1 warning`.
- Real full pipeline `exp_fs_seq_dom_hyp_smoke_20260713_102016_278700` passed with Neo4j:
  10 structure + 10 sequence + 10 domain evidence, 10 fused candidates, top-5 structure
  and candidate edges, 28 CTD conclusions, one hypothesis, and five PubMed evidence rows.
- Its rebuild preview checksum matched the frozen graph checksum exactly:
  `76d51d8e3537cdeafa34ab1f7fd9367591b8f80d2de60edbec30764fdb394f45`.
