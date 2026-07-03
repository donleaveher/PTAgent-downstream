"""Accession normalization and lightweight StructureCatalog behavior."""

from __future__ import annotations

from pkg.structure import (
    LocalStructureCatalog,
    StructureStatus,
    TsvStructureCatalog,
    normalize_accession,
)


def test_normalize_accession_common_forms() -> None:
    cases = {
        "P40763": ("P40763", "", "plain"),
        "P40763-2": ("P40763", "P40763-2", "isoform"),
        "sp|P40763|STAT3_HUMAN": ("P40763", "", "uniprot_pipe"),
        "AF-P40763-F1-model_v6.cif.gz": ("P40763", "", "alphafold_model"),
        "/tmp/AF-P40763-F1-model_v6.cif.gz": ("P40763", "", "alphafold_model"),
    }

    for raw, expected in cases.items():
        norm = normalize_accession(raw)
        assert (norm.accession, norm.isoform_accession, norm.source_form) == expected


def test_local_catalog_resolves_latest_alphafold_model_and_missing(tmp_path) -> None:
    (tmp_path / "AF-P40763-F1-model_v4.cif.gz").write_text("old", encoding="utf-8")
    latest = tmp_path / "AF-P40763-F1-model_v6.cif.gz"
    latest.write_text("new", encoding="utf-8")

    catalog = LocalStructureCatalog(tmp_path, source_version="afdb-v6")
    records = catalog.resolve(["sp|P40763|STAT3_HUMAN", "P40763-2", "UNKNOWN123"])

    pipe = records["sp|P40763|STAT3_HUMAN"]
    assert pipe.status is StructureStatus.AVAILABLE
    assert pipe.accession == "P40763"
    assert pipe.local_path == str(latest)
    assert pipe.source_version == "afdb-v6"
    assert pipe.provenance["source_form"] == "uniprot_pipe"

    isoform = records["P40763-2"]
    assert isoform.status is StructureStatus.AVAILABLE
    assert isoform.isoform == "P40763-2"
    assert isoform.local_path == str(latest)

    missing = records["UNKNOWN123"]
    assert missing.status is StructureStatus.MISSING
    assert missing.reason == "not_found_in_catalog"


def test_local_catalog_missing_directory_is_explainable(tmp_path) -> None:
    catalog = LocalStructureCatalog(tmp_path / "does-not-exist", source_version="afdb-v6")
    record = catalog.resolve(["P40763"])["P40763"]

    assert record.status is StructureStatus.MISSING
    assert record.reason == "query_structure_dir_not_found"
    assert record.source_version == "afdb-v6"


def test_tsv_catalog_reads_status_and_provenance(tmp_path) -> None:
    structure = tmp_path / "AF-P40763-F1-model_v6.cif.gz"
    structure.write_text("model", encoding="utf-8")
    catalog_file = tmp_path / "structure_catalog.tsv"
    catalog_file.write_text(
        "\t".join(
            [
                "accession",
                "structure_id",
                "source",
                "source_version",
                "format",
                "local_path",
                "status",
                "reason",
                "mean_plddt",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "P40763",
                "AF-P40763-F1-model_v6",
                "AlphaFoldDB",
                "v6",
                "cif.gz",
                str(structure),
                "available",
                "",
                "91.5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = TsvStructureCatalog(catalog_file)
    record = catalog.resolve(["AF-P40763-F1-model_v6.cif.gz"])[
        "AF-P40763-F1-model_v6.cif.gz"
    ]

    assert record.status is StructureStatus.AVAILABLE
    assert record.accession == "P40763"
    assert record.local_path == str(structure)
    assert record.mean_plddt == 91.5
    assert record.provenance["catalog_file"] == str(catalog_file)
