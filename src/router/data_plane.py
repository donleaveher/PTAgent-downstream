"""Data plane：Session、DataObject、Run 的 HTTP API（与 doc/data.md 一致）。"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from pydantic import BaseModel

from pkg.data_plane import get_data_plane_store, SYSTEM_SESSION_ID
from pkg.data_plane.pipeline_paths import ensure_pipeline_subdirs, generate_request_id, is_valid_request_id

data_plane_router = APIRouter(prefix="/ptagent-admin", tags=["data-plane"])


class SessionCreateBody(BaseModel):
    user_id: str | None = None


class SessionCursorBody(BaseModel):
    current_cursor_id: str | None = None


class PipelineRequestCreateBody(BaseModel):
    """创建或复用全流程目录根；`request_id` 省略时服务端生成 `prq_<hex>`。"""

    request_id: str | None = None
    session_id: str | None = None
    meta: dict[str, Any] | None = None


def _check_internal(authorization: str | None) -> bool:
    key = os.environ.get("PTAGENT_INTERNAL_API_KEY", "").strip()
    if not key:
        return True
    return authorization == f"Bearer {key}" or authorization == key


@data_plane_router.post("/api/data-plane/sessions")
def api_data_plane_session_create(body: SessionCreateBody) -> dict[str, Any]:
    store = get_data_plane_store()
    sid = store.create_session(user_id=body.user_id)
    return {"session_id": sid, "ok": True}


@data_plane_router.get("/api/data-plane/sessions/{session_id}")
def api_data_plane_session_get(session_id: str) -> dict[str, Any]:
    store = get_data_plane_store()
    row = store.get_session(session_id)
    if not row:
        raise HTTPException(404, "session not found")
    return row


@data_plane_router.put("/api/data-plane/sessions/{session_id}/cursor")
def api_data_plane_session_cursor(session_id: str, body: SessionCursorBody) -> dict[str, Any]:
    store = get_data_plane_store()
    if not store.get_session(session_id):
        raise HTTPException(404, "session not found")
    store.set_session_cursor(session_id, body.current_cursor_id)
    return {"ok": True}


@data_plane_router.get("/api/data-plane/data-objects/{object_id}")
def api_data_plane_object_get(object_id: str) -> dict[str, Any]:
    store = get_data_plane_store()
    row = store.get_data_object(object_id)
    if not row:
        raise HTTPException(404, "data object not found")
    return dict(row)


@data_plane_router.get("/api/data-plane/data-objects/{object_id}/path")
def api_data_plane_object_path(
    object_id: str,
    x_ptagent_internal: str | None = Header(default=None, alias="X-PTAGENT-Internal"),
) -> dict[str, str]:
    if not _check_internal(x_ptagent_internal):
        raise HTTPException(403, "internal API key required")
    store = get_data_plane_store()
    path = store.storage_path(object_id)
    if not path or not path.is_file():
        raise HTTPException(404, "data object or file missing")
    return {"object_id": object_id, "path": str(path)}


@data_plane_router.get("/api/data-plane/sessions/{session_id}/runs/{run_id}")
def api_data_plane_run_get(session_id: str, run_id: str) -> dict[str, Any]:
    store = get_data_plane_store()
    r = store.get_run(run_id)
    if not r or r.get("session_id") != session_id:
        raise HTTPException(404, "run not found")
    return r


@data_plane_router.post("/api/data-plane/pipeline-requests")
def api_data_plane_pipeline_request_create(body: PipelineRequestCreateBody) -> dict[str, Any]:
    """登记 `request_id`、创建 `data/pipelines/<id>/` 标准子目录，供上传与工具绑定。"""
    store = get_data_plane_store()
    if body.request_id is not None:
        raw = body.request_id.strip()
        if not raw:
            raise HTTPException(400, "若提供 request_id 则不可为空")
        if not is_valid_request_id(raw):
            raise HTTPException(400, "request_id 须为 prq_ 后接 12–64 位十六进制，或省略由服务端生成")
        rid = raw
    else:
        rid = generate_request_id()
    existing = store.get_pipeline_request(rid)
    if existing:
        return {
            "ok": True,
            "request_id": rid,
            "root_path": existing["root_path"],
            "existed": True,
        }
    root = ensure_pipeline_subdirs(rid)
    store.create_pipeline_request(
        rid,
        root,
        session_id=body.session_id,
        meta=body.meta or {},
    )
    return {"ok": True, "request_id": rid, "root_path": str(root), "existed": False}


@data_plane_router.get("/api/data-plane/pipeline-requests/{request_id}")
def api_data_plane_pipeline_request_get(request_id: str) -> dict[str, Any]:
    if not is_valid_request_id(request_id):
        raise HTTPException(400, "invalid request_id format")
    store = get_data_plane_store()
    row = store.get_pipeline_request(request_id)
    if not row:
        raise HTTPException(404, "pipeline request not found")
    return dict(row)


# --- 与 MCP 管理页一致的文档化说明（不单独占界面）---
@data_plane_router.get("/api/data-plane/contract", include_in_schema=True)
def api_data_plane_contract() -> dict[str, Any]:
    return {
        "mcpFileTools": "质谱/文件类工具：入参为 data_object_id 列表，禁止直接传主机路径。",
        "mcpIOTools": "UniProt、DeepXiv 等：走 RunKind.MCP_IO，以 accession/查询字串为参数，不经过 DataObject 大文件。",
        "systemSessionId": SYSTEM_SESSION_ID,
        "casanovoLlmSummaryExample": (
            "Casanovo 完成：provider=casanovo，共 N 条谱图预测；全量 JSON 已落盘，"
            "请仅用返回的 output_data_object_id / run_id 做后续步骤，勿在对话中重复大 JSON。"
        ),
    }
