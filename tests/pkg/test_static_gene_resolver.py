from __future__ import annotations

from config.settings import get_settings
from pkg.disease import StaticGeneResolver, get_gene_resolver, parse_static_gene_mapping


def test_parse_static_gene_mapping_skips_comments_and_extra_columns() -> None:
    mapping = parse_static_gene_mapping(
        [
            "# accession\tgene_symbol\n",
            "P40763\tSTAT3\tnote\n",
            "\n",
            "bad-single-column\n",
        ]
    )

    assert mapping == {"P40763": "STAT3"}


def test_static_gene_resolver_normalizes_alphafold_model_names(tmp_path) -> None:
    fixture = tmp_path / "genes.tsv"
    fixture.write_text("P40763\tSTAT3\n", encoding="utf-8")

    resolver = StaticGeneResolver.from_file(fixture)

    assert resolver.resolve(["AF-P40763-F1-model_v6.cif.gz", "MISSING"]) == {
        "AF-P40763-F1-model_v6.cif.gz": "STAT3"
    }


def test_get_gene_resolver_static_provider(monkeypatch, tmp_path) -> None:
    fixture = tmp_path / "genes.tsv"
    fixture.write_text("P40763\tSTAT3\n", encoding="utf-8")
    monkeypatch.setenv("PTAGENT_JWT__SECRET_KEY", "test-secret")
    monkeypatch.setenv("PTAGENT_ANNOTATION__GENE_RESOLVER_PROVIDER", "static")
    monkeypatch.setenv("PTAGENT_ANNOTATION__STATIC_GENE_MAPPING_FILE", str(fixture))
    get_settings.cache_clear()

    try:
        resolver = get_gene_resolver()
        assert resolver.resolve(["P40763"]) == {"P40763": "STAT3"}
    finally:
        get_settings.cache_clear()
