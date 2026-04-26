"""数据平面领域类型（与 doc/data.md 一致）。"""

from __future__ import annotations

from enum import Enum
from typing import TypedDict


class DataType(str, Enum):
    """物理落盘或结构化产物的粗粒度类型。"""

    RAW = "RAW"
    MGF = "MGF"
    MZML = "MZML"
    FASTA = "FASTA"
    TSV = "TSV"
    PLOT = "PLOT"
    INFERENCE_JSON = "INFERENCE_JSON"  # Casanovo 等整次 run 的 JSON
    JSON = "JSON"  # 通用小 JSON 摘要/缓存
    OTHER = "OTHER"


class RunStatus(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    SUCCESS = "Success"
    FAILED = "Failed"


class RunKind(str, Enum):
    """FILE_PIPELINE：走 DataObject 路径的推理/生信。MCP_IO：外部 API/网页，与大体量质谱无直接绑定。"""

    FILE_PIPELINE = "FILE_PIPELINE"
    MCP_IO = "MCP_IO"


# 无用户上下文时的默认 session，供仅注册 Run 的入口使用
SYSTEM_SESSION_ID = "dp-system"


class DataObjectRow(TypedDict, total=False):
    object_id: str
    session_id: str
    data_type: str
    storage_path: str
    meta_json: str
    file_hash: str | None
    file_size: int | None
    request_id: str | None


class RunRow(TypedDict, total=False):
    run_id: str
    session_id: str
    tool_name: str
    run_kind: str
    status: str
    input_object_ids: str
    output_object_ids: str
    parameters: str
    error_log: str | None
    created_at: str
    updated_at: str | None
    request_id: str | None
