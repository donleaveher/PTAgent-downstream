"""Materializer：把一次 run 的产出解包进关系图谱。

定位：execute_dag 跑完工具、产出结果文件之后的「旁路增强」步骤。
- 不懂任何工具的输出格式（格式知识全在 loaders/ 里）；
- 幂等：已 materialized 的结果文件跳过；MERGE 在稳定键上去重；
- de novo 只建主干 Sample→Spectrum→PSM→Peptide，不碰蛋白层/GDS。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from application.graph.loaders import get_loader
from pkg.data_plane.store import DataPlaneStore, get_data_plane_store
from pkg.graph import get_graph_store

logger = logging.getLogger(__name__)


# ───────────────────────── 内部小工具 ─────────────────────────
def _json_ids(run: dict[str, Any], key: str) -> list[str]:
    """input_object_ids / output_object_ids 在库里是 JSON 串，这里解成 list。"""
    return json.loads(run.get(key) or "[]")


def _already_materialized(dp: DataPlaneStore, object_id: str) -> bool:
    """结果文件的 meta_json 是否已盖过 materialized:true（防重复入图）。"""
    obj = dp.get_data_object(object_id) or {}
    meta = json.loads(obj.get("meta_json") or "{}")
    return bool(meta.get("materialized"))


# ───────────────────────── 主入口 ─────────────────────────
def materialize_run(run_id: str, *, force: bool = False) -> dict[str, Any]:
    """把一次 run 解包进图谱。

    Args:
        run_id: dp_run 主键。
        force:  True 则忽略 materialized 标记强制重跑（MERGE 幂等，重跑安全）。

    Returns:
        {"run_id", "status", "rows"}，status ∈
            ok         成功写入 rows 行
            skipped    结果文件已 materialized（force=False）
            empty      loader 没产出行（该 run 不是可入图形态 / 无 PSM）
            no_loader  该 tool_name 没有对应 loader → 跳过
            unknown_run 查无此 run
    """
    dp = get_data_plane_store()

    # ① 查 run
    run = dp.get_run(run_id)
    if not run:
        logger.warning("[materialize] run 不存在: %s", run_id)
        return {"run_id": run_id, "status": "unknown_run", "rows": 0}

    out_ids = _json_ids(run, "output_object_ids")

    # 幂等：结果文件都已入过图就跳过（先写 Neo4j、后标 SQLite；中途崩了重跑也安全）
    if not force and out_ids and all(_already_materialized(dp, oid) for oid in out_ids):
        logger.info("[materialize] run=%s 已 materialized，跳过", run_id)
        return {"run_id": run_id, "status": "skipped", "rows": 0}

    # ② 按 tool_name 选 loader（未知工具静默跳过，不是错误）
    loader = get_loader(run.get("tool_name", ""))
    if loader is None:
        logger.info("[materialize] run=%s tool=%r 无 loader，跳过",
                    run_id, run.get("tool_name"))
        return {"run_id": run_id, "status": "no_loader", "rows": 0}

    # ③ loader 拼扁平行（选文件 + 解析 + join，全在 loader 内部）
    rows = loader(dp, run)
    if not rows:
        logger.info("[materialize] run=%s loader 无产出（非可入图形态/无PSM）", run_id)
        return {"run_id": run_id, "status": "empty", "rows": 0}

    # ④ 分批 MERGE 写主干
    g = get_graph_store()
    n = g.merge_trunk(rows)
    # —— 数据库搜索范式才需要（de novo 不走）：
    #     pep_prot = loader_protein_edges(dp, run)
    #     g.merge_pep_prot(pep_prot); g.run_inference()   # 需 Neo4j 装 GDS 插件

    # ⑤ 成功后给结果文件盖章（顺序：先 Neo4j 后 SQLite）
    for oid in out_ids:
        dp.update_data_object_meta(oid, {"materialized": True, "graph_rows": n})

    logger.info("[materialize] run=%s 写入主干 %d 行", run_id, n)
    return {"run_id": run_id, "status": "ok", "rows": n}


def materialize_run_safe(run_id: str, *, force: bool = False) -> dict[str, Any]:
    """容错包装：供 pipeline 节点用——图谱是旁路增强，失败绝不拖垮主流程。"""
    try:
        return materialize_run(run_id, force=force)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[materialize] run=%s 失败（已隔离，不影响主 run）", run_id)
        return {"run_id": run_id, "status": "error", "rows": 0, "error": str(exc)}


__all__ = ["materialize_run", "materialize_run_safe"]