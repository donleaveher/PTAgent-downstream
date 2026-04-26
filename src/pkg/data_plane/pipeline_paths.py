"""全流程「企业级」目录：与前后端协定的 request_id 对应单根，子目录放各阶段产物。"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from config.paths import data_dir

# 子目录名（与 doc/data.md 中「统一地址」一致，勿随意改名）
DIR_INPUT = "input"
DIR_CONTEXT = "context"
DIR_DENOVO = "denovo"
DIR_SEARCH = "search"
DIR_SIMULATION = "simulation"
DIR_FIGURES = "figures"
DIR_REPORT = "report"
DIR_MISC = "artifacts"

_PIPELINE_SUBDIRS = (
    DIR_INPUT,
    DIR_CONTEXT,
    DIR_DENOVO,
    DIR_SEARCH,
    DIR_SIMULATION,
    DIR_FIGURES,
    DIR_REPORT,
    DIR_MISC,
)


def generate_request_id() -> str:
    return f"prq_{uuid.uuid4().hex}"


def is_valid_request_id(s: str) -> bool:
    s = s.strip()
    if not s or len(s) > 80:
        return False
    return bool(re.match(r"^prq_[0-9a-f]{12,64}$", s))


def pipeline_root_dir(request_id: str) -> Path:
    if not is_valid_request_id(request_id):
        raise ValueError(f"invalid request_id: {request_id!r}（应形如 prq_<hex>，由前后端共同约定或 POST pipeline-requests 获取）")
    return (data_dir() / "pipelines" / request_id).resolve()


def ensure_pipeline_subdirs(request_id: str) -> Path:
    """创建标准子目录，返回该 request 根路径。"""
    root = pipeline_root_dir(request_id)
    for name in _PIPELINE_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "README.txt").write_text(
        "PTAgent 全流程目录：input/context/denovo/search/simulation/figures/report/artifacts。request_id 与库表 dp_pipeline_request 一致。\n",
        encoding="utf-8",
    )
    return root


def require_registered_pipeline_request(request_id: str, store: object) -> None:
    """
    供 ingest / Casanovo 等调用：先校验格式，再要求已在 ``dp_pipeline_request`` 中登记
   （由 ``POST .../pipeline-requests`` 创建）。
    """
    if not is_valid_request_id(request_id):
        raise ValueError(
            f"非法 request_id: {request_id!r}，须为 prq_ 后接 12–64 位十六进制"
        )
    row = store.get_pipeline_request(request_id)
    if not row:
        raise ValueError(
            "request_id 未登记：请先调用 POST /ptagent-admin/api/data-plane/pipeline-requests 再上传或跑工具"
        )
