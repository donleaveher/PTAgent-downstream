"""Smoke test for the real Foldseek + AlphaFold structure-neighbor path.

This script downloads one AlphaFold query structure if needed, runs the local
Foldseek binary against the local AlphaFold Foldseek DB, and verifies that the
result is persisted through the PTAgent MySQL evidence/fusion tables.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - local setup issue only
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

os.environ.setdefault("PTAGENT_JWT__SECRET_KEY", "dev")
os.environ.setdefault("PTAGENT_EXPERIMENT_DATABASE__HOST", "127.0.0.1")
os.environ.setdefault("PTAGENT_EXPERIMENT_DATABASE__PORT", "3307")
os.environ.setdefault("PTAGENT_EXPERIMENT_DATABASE__USER", "ptagent")
os.environ.setdefault("PTAGENT_EXPERIMENT_DATABASE__PASSWORD", "ptagent_change_me")
os.environ.setdefault("PTAGENT_EXPERIMENT_DATABASE__DATABASE", "ptagent_experiment")

from application.orchestration import (  # noqa: E402
    DownstreamPipelineConfig,
    pipeline_status,
    run_downstream_pipeline,
)
from config import StructureSettings  # noqa: E402
from pkg.experiment import (  # noqa: E402
    ExperimentBundle,
    ExperimentContext,
    ExperimentGroup,
    GroupRole,
    MySQLExperimentStore,
    PeptideRecord,
    ProteinQuantification,
    ProteinRecord,
)
from pkg.structure import build_structure_search_provider  # noqa: E402


USER_AGENT = "PTAgent-foldseek-real-smoke/1.0"


def _experiment_id(prefix: str) -> str:
    return prefix + datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _fetch_json(url: str, *, timeout: int) -> object:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, target: Path, *, timeout: int, force: bool) -> None:
    if target.exists() and target.stat().st_size > 0 and not force:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            shutil.copyfileobj(response, tmp)
    tmp_path.replace(target)


def download_alphafold_cif(
    accession: str,
    *,
    query_structure_dir: Path,
    timeout: int,
    force: bool,
) -> tuple[Path, dict[str, object]]:
    api_url = f"https://alphafold.ebi.ac.uk/api/prediction/{accession}"
    payload = _fetch_json(api_url, timeout=timeout)
    rows = payload if isinstance(payload, list) else [payload]
    candidates = [row for row in rows if isinstance(row, dict) and row.get("cifUrl")]
    if not candidates:
        raise RuntimeError(f"AlphaFold API returned no cifUrl for {accession}: {api_url}")
    record = sorted(
        candidates,
        key=lambda row: int(row.get("latestVersion") or 0),
        reverse=True,
    )[0]
    cif_url = str(record["cifUrl"])
    filename = Path(urlparse(cif_url).path).name
    if not filename:
        raise RuntimeError(f"could not derive CIF filename from URL: {cif_url}")
    target = query_structure_dir / filename
    _download(cif_url, target, timeout=timeout, force=force)
    return target, record


def _bundle(exp_id: str, accession: str, gene: str, organism: str) -> ExperimentBundle:
    protein_id = f"prot_{accession.lower()}"
    peptide_id = f"pep_{accession.lower()}"
    return ExperimentBundle(
        context=ExperimentContext(
            experiment_id=exp_id,
            session_id="foldseek_real_smoke",
            title="Real Foldseek AlphaFold smoke test",
            raw_text="Real AlphaFold query structure + local Foldseek DB smoke test",
            disease=["structure-smoke"],
            pathway=["foldseek-alphafold"],
            organism=organism,
            assay="DIA",
        ),
        groups=[
            ExperimentGroup(group_id="g_case", label="Case", role=GroupRole.CASE),
            ExperimentGroup(group_id="g_ctrl", label="Control", role=GroupRole.CONTROL),
        ],
        proteins=[
            ProteinRecord(
                protein_id=protein_id,
                accession=accession,
                gene=gene,
                organism=organism,
                peptide_ids=[peptide_id],
                meta={"smoke": "real_foldseek_alphafold"},
            )
        ],
        peptides=[
            PeptideRecord(
                peptide_id=peptide_id,
                peptidoform="PEPTIDEK",
                stripped_sequence="PEPTIDEK",
                protein_id=protein_id,
                spectrum_ids=[f"spec_{accession.lower()}"],
                confidence=0.98,
                group_label="Case",
                abundance=1000.0,
            )
        ],
    )


def _quantifications(exp_id: str, accession: str) -> list[ProteinQuantification]:
    protein_id = f"prot_{accession.lower()}"
    return [
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id=protein_id,
            group_id="g_case",
            sample_id="case_1",
            abundance=120.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id=protein_id,
            group_id="g_case",
            sample_id="case_2",
            abundance=130.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id=protein_id,
            group_id="g_ctrl",
            sample_id="ctrl_1",
            abundance=10.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id=protein_id,
            group_id="g_ctrl",
            sample_id="ctrl_2",
            abundance=11.0,
        ),
    ]


def parse_args() -> argparse.Namespace:
    default_binary = os.environ.get(
        "PTAGENT_STRUCTURE__FOLDSEEK_BINARY",
        "/Users/tourbillion/foldseek/bin/foldseek",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", default="", help="Optional fixed experiment_id.")
    parser.add_argument("--snapshot-version", default="1.0")
    parser.add_argument("--accession", default="P40763", help="Query UniProt accession.")
    parser.add_argument("--gene", default="STAT3")
    parser.add_argument("--organism", default="Homo sapiens")
    parser.add_argument("--foldseek-binary", default=default_binary)
    parser.add_argument(
        "--alphafold-db",
        default=os.environ.get(
            "PTAGENT_STRUCTURE__ALPHAFOLD_DB",
            "data/alphafold/afdb/alphafold_swissprot",
        ),
    )
    parser.add_argument(
        "--query-structure-dir",
        default=os.environ.get(
            "PTAGENT_STRUCTURE__QUERY_STRUCTURE_DIR",
            "data/structures",
        ),
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--min-coverage", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--force-download", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    exp_id = args.experiment_id or _experiment_id("exp_foldseek_real_smoke_")
    accession = args.accession.strip()
    if not accession:
        raise SystemExit("--accession must be non-empty")

    query_structure_dir = _resolve_path(args.query_structure_dir)
    alphafold_db = _resolve_path(args.alphafold_db)
    foldseek_binary = str(_resolve_path(args.foldseek_binary)) if "/" in args.foldseek_binary else args.foldseek_binary

    downloaded, af_record = download_alphafold_cif(
        accession,
        query_structure_dir=query_structure_dir,
        timeout=args.timeout,
        force=args.force_download,
    )
    latest_version = str(af_record.get("latestVersion") or "unknown")

    store = MySQLExperimentStore.from_settings()
    store.initialize_schema()
    store.save_bundle(_bundle(exp_id, accession, args.gene, args.organism))
    store.add_quantifications(_quantifications(exp_id, accession))

    structure_settings = StructureSettings(
        provider="foldseek",
        foldseek_binary=foldseek_binary,
        alphafold_db=str(alphafold_db),
        query_structure_dir=str(query_structure_dir),
        top_k=args.top_k,
        min_score=args.min_score,
        min_coverage=args.min_coverage,
        exclude_self=True,
        version=f"alphafold-v{latest_version}-real-smoke-{exp_id}",
    )
    structure_provider = build_structure_search_provider(structure_settings)

    result = run_downstream_pipeline(
        exp_id,
        repository=store,
        config=DownstreamPipelineConfig(
            snapshot_version=args.snapshot_version,
            pipeline_version="foldseek-real-smoke",
            top_k=args.top_k,
            structure_provider=structure_provider,
            neighbor_provider_names=("structure.foldseek",),
            allow_unresolved_hypotheses=True,
        ),
        steps=["differential", "neighbor_search", "freeze", "report"],
    )

    structure_runs = store.list_structure_search_runs(exp_id)
    structure_statuses = store.list_structure_statuses(exp_id)
    structure_evidence = store.list_structure_neighbor_evidence(exp_id)
    neighbor_runs = store.list_neighbor_search_runs(exp_id)
    neighbor_evidence = store.list_neighbor_evidence(exp_id)
    fused_candidates = store.list_fused_candidates(exp_id)

    print("experiment_id:", exp_id)
    print("completed:", result.completed)
    print("failed_step:", result.failed_step)
    print("statuses:", result.step_statuses())
    print("pipeline_status:", pipeline_status(exp_id, repository=store))
    print("downloaded_structure:", str(downloaded))
    print("alphafold_latest_version:", latest_version)
    print("alphafold_cif_url:", af_record.get("cifUrl"))
    print("foldseek_binary:", foldseek_binary)
    print("alphafold_db:", str(alphafold_db))
    print("query_structure_dir:", str(query_structure_dir))
    print("structure_statuses:", len(structure_statuses))
    print("structure_search_runs:", len(structure_runs))
    print("structure_neighbor_evidence:", len(structure_evidence))
    print("neighbor_search_runs:", len(neighbor_runs))
    print("neighbor_evidence:", len(neighbor_evidence))
    print("fused_candidates:", len(fused_candidates))
    print("reports:", len(store.list_reports(exp_id)))

    for row in structure_statuses[:5]:
        print(
            "structure_status_preview:",
            row.raw_accession,
            row.status,
            row.reason,
        )
    for row in structure_evidence[:10]:
        print(
            "structure_evidence_preview:",
            row.query_accession,
            "->",
            row.target_accession,
            "score=",
            row.score,
            "coverage=",
            row.coverage,
            "rank=",
            row.rank,
        )
    for row in fused_candidates[:10]:
        print(
            "fused_candidate_preview:",
            row.query_accession,
            "->",
            row.target_id,
            "rank=",
            row.fusion_rank,
            "channels=",
            row.support_channels,
        )

    if not result.completed:
        raise SystemExit(1)
    if structure_statuses:
        raise SystemExit("real Foldseek smoke produced structure status rows; inspect previews above")
    if not structure_evidence or not neighbor_evidence or not fused_candidates:
        raise SystemExit("real Foldseek smoke produced no persisted neighbor evidence")


if __name__ == "__main__":
    try:
        main()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SystemExit(f"AlphaFold download failed: {type(exc).__name__}: {exc}") from exc
