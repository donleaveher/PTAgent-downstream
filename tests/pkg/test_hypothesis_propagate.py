"""注释传递(共识 + 按蛋白分组出处)纯函数测试。"""
from __future__ import annotations

import pytest

from pkg.hypothesis import transfer_annotations

_NEIGHBORS = [
    {"id": "n1", "score": 0.9, "proteins": {
        "P1": {"go": ["GO:1", "GO:2"], "ec": [], "interpro": []}}},
    {"id": "n2", "score": 0.8, "proteins": {                     # n2 映射到两个蛋白(共享肽)
        "P1": {"go": ["GO:1"], "ec": ["1.1.1.1"], "interpro": []},
        "P2": {"go": ["GO:1"], "ec": [], "interpro": []}}},
    {"id": "n3", "score": 0.2, "proteins": {
        "P3": {"go": ["GO:9"], "ec": [], "interpro": []}}},
]


def test_consensus_with_protein_provenance() -> None:
    preds = transfer_annotations(_NEIGHBORS)
    top = preds[0]
    assert top["predicted"] == "GO:1"                           # 两个相似邻居共持 → 置信最高
    assert top["sim"] == pytest.approx((0.9 + 0.8) / 2)
    assert top["consensus"] == pytest.approx(2 / 3)
    assert top["confidence"] == pytest.approx(0.85 * (2 / 3))
    # support 带出处：哪个邻居、经由它的哪些蛋白
    via = {s["neighbor"]: s["via"] for s in top["support"]}
    assert set(via) == {"n1", "n2"}
    assert via["n1"] == ["P1"]
    assert sorted(via["n2"]) == ["P1", "P2"]                    # n2 两个蛋白都带 GO:1

    go9 = next(p for p in preds if p["predicted"] == "GO:9")
    assert go9["confidence"] == pytest.approx(0.2 * (1 / 3))    # 单弱邻居 → 置信很低
    assert preds == sorted(preds, key=lambda p: (-p["confidence"], p["attr_type"], p["predicted"]))


def test_min_confidence_and_top_n() -> None:
    preds = transfer_annotations(_NEIGHBORS, min_confidence=0.1)
    assert all(p["confidence"] >= 0.1 for p in preds)
    assert "GO:9" not in {p["predicted"] for p in preds}        # 0.0667 < 0.1 被挡掉

    top2 = transfer_annotations(_NEIGHBORS, top_n=2)
    assert [p["predicted"] for p in top2] == ["GO:1", "GO:2"]


def test_neighbor_without_proteins_dilutes_consensus() -> None:
    # 没注释的邻居(novel)：进分母、不支持任何属性 → 拉低共识
    neighbors = [
        {"id": "a", "score": 0.9, "proteins": {"P1": {"go": ["GO:1"], "ec": [], "interpro": []}}},
        {"id": "b", "score": 0.9, "proteins": {}},
    ]
    go1 = next(p for p in transfer_annotations(neighbors) if p["predicted"] == "GO:1")
    assert go1["consensus"] == pytest.approx(1 / 2)
    assert [s["neighbor"] for s in go1["support"]] == ["a"]


def test_empty_neighbors() -> None:
    assert transfer_annotations([]) == []
