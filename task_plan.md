# Task Plan: Neighbor Search Refactor

## Goal
Refactor neighbor search/fusion into a reusable provider-driven layer so hypothesis generation consumes persisted fused candidates instead of directly invoking providers.

## Phases
- [x] Phase 1: Read project docs and map current implementation.
- [x] Phase 2: Design minimal code changes aligned with existing patterns.
- [x] Phase 3: Implement provider-driven neighbor search and compatibility wrapper.
- [x] Phase 4: Update pipeline and hypothesis generation to consume fused candidates.
- [x] Phase 5: Run focused tests and fix regressions.
- [x] Phase 6: Summarize changes and residual risks.

## Key Questions
1. Where are neighbor candidates, fused candidates, and run metadata persisted today?
2. Which pipeline entry points currently call neighbor fusion and hypothesis generation?
3. How much can hypothesis generation be changed without breaking existing tests and contracts?

## Decisions Made
- Use a compatibility wrapper for existing `generate_fused_neighbor_candidates(...)` callers while routing through the new service.
- Split structure provider execution into `run_structure_search(...)` so `neighbor_search` can consume persisted structure evidence and `hypothesis_generation` no longer calls providers.
- Keep `confidence` as best channel score and record `fused_confidence` separately because RRF scores are rank scores, not calibrated biological confidence.
- Default pipeline should not special-case structure search. Structure now enters `neighbor_search` as `StructureSearchNeighborProvider`; `structure_search` remains only as an optional precompute/backfill step.

## Errors Encountered
- `pytest` and `python` were not on PATH; used `.venv/bin/python -m pytest`.

## Status
**Completed** - Generic neighbor evidence schema and persistence are implemented.

## Follow-up: Provider Abstraction
- [x] Define `NeighborProviderResult` and provider registry in `pkg.retrieval`.
- [x] Convert sequence and structure providers to return unified results.
- [x] Move provider evidence persistence into `NeighborSearchService`.
- [x] Add config-driven provider name resolution.
- [x] Update tests and docs.
- [x] Move structure provider implementations into `pkg.retrieval.providers.structure`.
- [x] Move sequence provider implementation into `pkg.retrieval.providers.sequence`.
- [x] Define `ProviderPersistenceAdapter` protocol.
- [x] Move structure run/evidence/status persistence into `StructureEvidencePersistenceAdapter`.
- [x] Route `neighbor_search` persistence through adapter list.
- [x] Define generic `NeighborSearchRun`, `NeighborEvidence`, and `NeighborEvidenceStatus`.
- [x] Add repository/MySQL persistence for generic neighbor evidence rows.
- [x] Persist provider results into generic neighbor evidence schema.

## Follow-up Verification
- Full suite after provider abstraction: `243 passed, 1 skipped, 1 warning`.
- After clarifying multi-provider names and adding coverage: `244 passed, 1 skipped, 1 warning`.
- After moving structure providers into `pkg.retrieval.providers`: `245 passed, 1 skipped, 1 warning`.
- After moving sequence provider into `pkg.retrieval.providers`: focused tests `17 passed`; full suite `246 passed, 1 skipped, 1 warning`.
- After decoupling provider persistence adapters: focused tests `19 passed`; full suite `248 passed, 1 skipped, 1 warning`.
- Generic neighbor evidence schema focused tests: `33 passed`.
- After generic neighbor evidence schema: full suite `250 passed, 1 skipped, 1 warning`.

---

# Task Plan: Deep-Search Evidence Closure

## Goal
Persist each literature evidence record, freeze it with the experiment snapshot, and render its verdict-specific references in the report.

## Phases
- [x] Phase 1: Map existing deep-search, snapshot, report, and repository contracts.
- [x] Phase 2: Add evidence domain model, schema, repository, and MySQL persistence.
- [x] Phase 3: Persist evidence and link verdict history to evidence IDs.
- [x] Phase 4: Include frozen evidence in manifests and layered reports.
- [x] Phase 5: Add focused regression coverage and verify MySQL smoke behavior.

## Decisions Made
- Keep `AnnotationHistory` as the verdict event ledger; introduce `DeepSearchEvidence` as the immutable evidence ledger.
- Store references, source/version, query, stance, snippet, provenance, and retrieval time. Do not store full paper text.
- Generate reports only from snapshot manifest content, never from live evidence rows.

## Errors Encountered
- Full-suite regression: two tests asserted the previous fixed report section count
  of eight. Updated their contract to nine after adding the frozen evidence section.

## Status
**Completed** - Evidence persistence, freeze/report integration, fixture smoke, and
regression coverage are complete. The fixture MySQL smoke is ready for manual execution.

---

# Task Plan: Real Literature MCP Integration

## Goal
Replace the deep-search production placeholder with a configured MCP-backed literature
source that validates results, retries transient failures, and preserves conservative
evidence stances.

## Phases
- [x] Phase 1: Inspect the broker client, DeepXiv convention, and existing MCP adapters.
- [x] Phase 2: Add deep-search MCP settings and a schema-normalizing source adapter.
- [x] Phase 3: Set the default factory to use the real MCP adapter and add a no-write smoke.
- [x] Phase 4: Cover normal results, schema failures, retries, and default factory behavior.
- [ ] Phase 5: Document environment setup and manual real-MCP verification. (ready for manual smoke)

## Decisions Made
- Use the existing MCP broker client and the existing default DeepXiv convention:
  tool `deepxiv_search`, arguments `query` and `top_k`.
- Only MCP-provided stance fields can become support/refute. Missing or unknown stance is
  persisted as neutral, so it cannot promote or refute a hypothesis automatically.
- A malformed non-empty MCP result is a hard failure, not an empty literature result.
- The integration retries call failures with a bounded backoff and exposes an explicit
  source error after the final attempt.

## Errors Encountered
- Full-suite regression: the legacy test expected the production source factory to raise
  `NotImplementedError`. Updated it to assert construction of the real MCP adapter
  without invoking the network.

## Status
**Currently in Phase 5** - Code and documentation are verified; awaiting the no-write
real-MCP smoke against the locally configured broker.

---

# Task Plan: Self-Hosted PubMed MCP

## Goal
Deploy a PTAgent-owned PubMed/Europe PMC MCP service and route downstream
deep-search retrieval directly to it, without relying on upstream code or an
external Provider repository.

## Phases
- [x] Phase 1: Evaluate the selected server, pin a release, and check local runtime.
- [x] Phase 2: Download the pinned upstream source and map its actual tool schema.
- [x] Phase 3: Add an isolated Docker Compose service and direct literature endpoint config.
- [x] Phase 4: Adapt the PubMed search output into PTAgent EvidenceRecord rows.
- [x] Phase 5: Build/start the local service and complete the requested no-write MCP validation.
  - [x] Add a direct, no-write MCP protocol smoke test.
  - [x] Build/start the local service and run the direct smoke test successfully.
- [x] Phase 6: Run the fixture-backed MySQL evidence smoke after human approval.

## Decisions Made
- Use cyanheads/pubmed-mcp-server v2.9.8 as the first and only literature recall
  service. It provides PubMed, Europe PMC, metadata, full-text, citations, and MeSH.
- Run the third-party service separately from the PTAgent Python process. Keep its
  source and dependencies in an ignored runtime directory, with version and checksum
  documented by PTAgent scripts.
- The downstream source connects to a dedicated literature MCP endpoint. This network
  direction is unrelated to the upstream proteomics pipeline.

## Status
**Completed** - `pubmed-mcp` is running locally; direct MCP, adapter, and fixture-backed
MySQL persistence smoke tests passed.

## Errors Encountered
- 2026-07-13: Initial Docker Hub pulls timed out because the active Clash node had an
  unstable Docker Hub route. Switching to another node resolved it; image build and
  service startup then completed successfully.

---

# Task Plan: Persisted Real PubMed Smoke

## Goal
Create and run a clearly labeled, isolated MySQL test experiment that retrieves real
PubMed records and verifies their evidence, history, snapshot, and report lifecycle.

## Phases
- [x] Phase 1: Confirm a real target experiment is not already available in local MySQL.
- [x] Phase 2: Add a minimal real-PubMed persistence smoke script.
- [x] Phase 3: Run the script against the local PubMed MCP and inspect persisted output.
- [x] Phase 4: Record results and deliver the reproducible command.

## Decisions Made
- Use an isolated `STAT3 × Lupus Nephritis` test experiment because local MySQL contains
  only fixture smoke experiments, not a user-provided biological experiment.
- Preserve the PubMed adapter's conservative policy: all retrieved articles remain
  `neutral`, so the smoke validates evidence persistence rather than biological proof.

## Status
**Completed** - Real PubMed retrieval persisted five neutral evidence records for
`exp_real_pubmed_smoke_20260713_044423_103466`; its snapshot and report both passed
their evidence checks.

---

# Task Plan: Full Downstream Pipeline Smoke

## Goal
Run the complete downstream pipeline on an isolated test experiment, using available
real local providers and the live local PubMed MCP where supported.

## Phases
- [x] Phase 1: Inspect the pipeline's required providers, assets, and runtime services.
- [x] Phase 2: Select the strongest available isolated smoke path and record limitations.
- [x] Phase 3: Run the full pipeline and inspect each step's persisted status.
- [x] Phase 4: Verify the frozen report and document the resulting evidence boundary.

## Key Questions
1. Which pipeline channels can use live data locally, and which require fixtures?
2. Can the test reach hypothesis and deep-search without relying on unavailable services?
3. Does the resulting frozen report preserve the downstream provenance correctly?

## Decisions Made
- Extend the existing three-channel real-data smoke with an opt-in deep-search flag,
  retaining its default no-network behavior for routine runs.
- The run will use real Foldseek, local UniProt-derived sequence/domain data, local CTD,
  and live PubMed. It will use the existing static gene resolver and in-memory graph,
  because a real UniProt MCP and running Neo4j service are not available locally.

## Status
**Completed** - The strongest available downstream pipeline completed for
`exp_fs_seq_dom_hyp_smoke_20260713_051913_232984`; its frozen report contains all five
real PubMed records. Production UniProt MCP and persistent Neo4j remain separate
external integration work.

## Errors Encountered
- 2026-07-13: A read-only preflight shell loop accidentally used zsh's reserved `path`
  variable, so later commands in that one shell could not find executables. It did not
  modify the system or containers; rerun the checks using a non-reserved variable.
- 2026-07-13: Two pipeline failure-isolation tests passed unexpectedly while the local
  PubMed service was running because `literature_source=None` selects the production
  default. Replaced that implicit environment dependency with an explicit failing test
  source; focused tests and the full suite now pass.

---

# Task Plan: Candidate-Gene PubMed Fallback

## Goal
When the original protein's PubMed query returns no records, retrieve clearly labeled
supplementary literature using the hypothesis's candidate-neighbor genes and disease.

## Phases
- [x] Phase 1: Trace the existing hypothesis derivation and PubMed adapter contracts.
- [x] Phase 2: Add an auditable zero-result candidate-gene fallback and configuration.
- [x] Phase 3: Add unit coverage and run a live no-write fallback verification.
- [x] Phase 4: Document query semantics and complete regression verification.

## Decisions Made
- Define “no direct evidence” mechanically as zero records from the original-protein
  PubMed query. A `neutral` result remains an observed record, not a negative finding.
- Candidate fallback records remain `neutral` and include query scope, candidate gene,
  and primary-query provenance so they cannot be mistaken for direct protein evidence.
- Omit the original protein's organism from fallback queries because candidate neighbors
  may be cross-species; retain the exact fallback query in evidence provenance.

## Status
**Completed** - Candidate-gene fallback is unit-tested and live-verified; direct-query
behavior is unchanged, and fallback records carry explicit provenance labels.

---

# Task Plan: Persisted Candidate-Fallback Smoke Assertions

## Goal
Make the full downstream smoke able to assert, on demand, that a zero-result primary
query used an expected candidate-gene PubMed fallback and that the resulting evidence
survived freezing.

## Phases
- [x] Phase 1: Inspect the existing smoke output and persisted fallback experiment.
- [x] Phase 2: Add opt-in CLI assertions without changing the default smoke behavior.
- [x] Phase 3: Run the forced-fallback full pipeline and focused regression checks.
- [x] Phase 4: Record verification and deliver the reproducible command.

## Decisions Made
- Keep fallback assertions opt-in because normal biological inputs may legitimately use
  the primary query path.
- Verify the frozen snapshot rather than require report prose to contain internal query
  provenance; the snapshot is the immutable evidence artifact.

## Status
**Completed** - The real-data smoke has opt-in fallback assertions; the forced
fallback run and the complete regression suite pass.

## Verification
- `PYTHONPATH=src .venv/bin/python scripts/smoke/foldseek_sequence_domain_hypothesis_real_smoke.py --include-deep-search --expect-candidate-fallback --gene PTAGENT_NONEXISTENT_GENE_987654`
  passed for `exp_fs_seq_dom_hyp_smoke_20260713_060234_001623` with five JAK1/Lupus
  fallback records matching the five frozen snapshot records.
- `git diff --check && .venv/bin/python -m pytest -q` passed: `268 passed, 1 skipped,
  1 warning`.

---

# Task Plan: Real Neo4j KG Smoke

## Goal
Exercise the existing MySQL-to-Neo4j graph projection against the local Neo4j service,
including graph traversal and isolated experiment-workspace cleanup.

## Phases
- [x] Phase 1: Confirm the local Neo4j service accepts authenticated Cypher commands.
- [x] Phase 2: Inspect the GraphStore contract and existing in-memory projection coverage.
- [x] Phase 3: Add a minimal, isolated real MySQL + Neo4j smoke script and its runbook.
- [x] Phase 4: Run it against the local service, then run the regression suite.
- [x] Phase 5: Record results and identify the next Neo4j integration boundary.

## Decisions Made
- Test the already implemented `Neo4jGraphStore` and `project_experiment_kg` rather than
  create a second production graph path.
- Seed two disposable MySQL experiments so `drop_experiment` can demonstrate that it
  removes only the target workspace and preserves another experiment plus general facts.
- Do not destroy the Neo4j volume or general nodes during the smoke; remove only the
  isolated target experiment's workspace edges and nodes.

## Status
**Completed** - The local Neo4j integration is smoke-tested against real MySQL; the
remaining work is full-pipeline Neo4j selection, freeze export, and production hardening.

## Verification
- Real MySQL + Neo4j smoke passed for
  `exp_neo4j_smoke_20260713_085804_814273`: constraints, two projections, traversals,
  re-projection idempotence, and experiment-workspace isolation all passed.
- `git diff --check && .venv/bin/python -m pytest -q` passed: `268 passed, 1 skipped,
  1 warning`.

---

# Task Plan: Neo4j Smoke State Output

## Goal
Make the real Neo4j smoke print inspectable KG and structural-evidence states before
the disposable experiment workspace is cleaned up.

## Phases
- [x] Phase 1: Identify the persisted graph and structural-evidence records available to the smoke.
- [x] Phase 2: Add deterministic, JSON-formatted state output and document its meaning.
- [x] Phase 3: Run the real smoke and regression checks.

## Decisions Made
- Report the primary test experiment only, before `drop_experiment`, so output represents
  the successfully projected graph rather than the expected post-cleanup empty workspace.
- Include MySQL `StructureSearchRun` and `StructureNeighborEvidence` alongside their
  projected `STRUCTURAL_NEIGHBOR` graph edge; no full structure file is stored in Neo4j.

## Status
**Completed** - The smoke prints its KG and MySQL structural-evidence states before
workspace cleanup; output fields are documented and regression-verified.

## Verification
- Real run `exp_neo4j_smoke_20260713_091450_798951` printed matching graph and MySQL
  structure/sequence state: one `STRUCTURAL_NEIGHBOR` with `run_id`, `evidence_id`,
  rank 1, score 0.95, coverage 0.8; one same-target sequence evidence with score 0.88;
  and one `CANDIDATE_NEIGHBOR` that references both IDs.
- `git diff --check && .venv/bin/python -m pytest -q` passed: `268 passed, 1 skipped,
  1 warning`.

---

# Task Plan: Neo4j Production Hardening

## Goal
Execute `docs/neo4j-improvement-plan.md` in dependency order until Neo4j has stable
identities, verified evidence, atomic projections, isolated queries, frozen graph
manifests, GNN-ready properties, and an explicit migration path.

## Phases
- [x] Phase 0: Review current code and live Neo4j state; write improvement plan.
- [x] Phase 1: Stable entity identity.
- [x] Phase 2: Stable relation identity and evidence integrity.
- [x] Phase 3: Atomic projection and stale-edge reconciliation.
- [x] Phase 4: Verdict synchronization and query isolation.
- [x] Phase 5: Frozen/recoverable graph snapshots.
- [x] Phase 6: Neo4j-native and GNN-ready property model.
- [x] Phase 7: Lifecycle and operational hardening.
- [x] Phase 8: Explicit migration and final real-service validation.

## Decisions Made
- Treat the improved graph as schema v2; do not silently mix existing v1 data.
- Keep MySQL as the only fact source and make Neo4j fully rebuildable.
- Never perform destructive graph migration automatically; migration defaults to dry-run.

## Status
**Completed** - Schema v2 hardening, operations, migration tooling, and real-service
validation are complete.

## Final Verification
- Full regression: `280 passed, 1 skipped, 1 warning`.
- Neo4j Compose is healthy on pinned `5.26.28-community`; Browser/Bolt bind only localhost.
- Real MySQL→Neo4j smoke projected 10 nodes/10 edges, verified isolation/reprojection,
  and removed both disposable workspaces.
- Full experiment `exp_fs_seq_dom_hyp_smoke_20260713_102016_278700` completed Foldseek,
  sequence/domain fusion, PubMed deep-search, Neo4j projection, freeze, and report.
- Rebuild dry-run produced graph checksum
  `76d51d8e3537cdeafa34ab1f7fd9367591b8f80d2de60edbec30764fdb394f45`, exactly
  matching the frozen snapshot without changing Neo4j.

## Errors Encountered
- The first Phase 1 patch assumed relative imports in `pkg.graph.__init__`; the package
  uses absolute imports. The failed patch applied no files and was regenerated against
  the actual export structure.
- Phase 2 focused tests exposed two intentionally obsolete expectations: a GENERAL
  structural edge still carrying an experiment evidence ID, and a fused test candidate
  whose structure evidence targeted another protein. Tests now assert version-stable
  GENERAL provenance and seed aligned sequence evidence for the same target.
- First real Phase 3 smoke found that the new Gene `symbol` existed only inside
  `props_json`, while Cypher traversal reads a top-level scalar. Identity and provenance
  fields are now promoted to native Neo4j properties before rerunning the smoke.
- The next smoke showed structural edges were present in Neo4j but the smoke queried the
  pre-normalized mixed-case accession. Smoke graph lookups now use the same canonical
  Protein key function as production projection.
- Phase 6 tests caught `_graph_manifest` inserted inside `_add_fused_candidate_edge`,
  making valid candidates silently disappear. The helper was moved after the complete
  candidate function before updating Comparison-node expectations.

## Errors Encountered
- Initial smoke preflight imported `project_experiment_kg` from the namespace package
  `application.graph`, which does not re-export it. The script now imports the concrete
  `application.graph.project_kg` module, matching the existing projection tests.
- First real run showed that fixed fixture tokens would merge general test nodes across
  multiple runs. Fixture tokens now include a SHA-256 fragment of each experiment ID so
  general smoke facts are unique and never overwrite one another's `mysql_ref`.
- Initial fixture labeled a candidate as structure+sequence but did not persist a sequence
  evidence row, and its structure and fused targets differed. It now seeds a real generic
  sequence run/evidence/status for the same target and asserts evidence-ID alignment.
