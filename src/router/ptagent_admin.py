"""PTAgent 管理：MCP 资源、Agent/Team CRUD 与 LLM/实验等 API。静态页由 ``PTAgent-frontend`` 边缘服务提供。"""

from __future__ import annotations

import uuid
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import get_mcp_settings
from config.paths import data_dir, project_root
from config.mcp_conventions import workflow_data_key_catalog
from pkg.agent.contracts import AgentSpec
from pkg.agent.debug_support import validate_agent
from application.agent import (
    agent_spec_to_record,
    get_registry_store,
    record_to_agent_spec,
    record_to_team,
)
from pkg.agent.runner import compile_llm_client, run_invocation, run_single_agent_graph
from pkg.agent._internal.team_graph import fork_warnings, validate_team_graph
from pkg.agent.team import build_team_mcp_workflow, team_requires_llm
from pkg.llm.model_catalog import list_chat_models_for_ui
from application.ptagent_admin.uniprot_taxonomy import taxonomy_search_for_ui
from pkg.llm.openai_runtime import (
    chat_completion_messages,
    get_openai_settings_for_ui,
    iter_chat_completion_messages_stream,
    openai_api_configured,
    test_openai_chat,
)
from application.data_plane.ingest import register_file_as_data_object
from application.workflow.llm_workflow import fallback_workflow_from_text, parse_workflow_from_text
from pkg.data_plane.pipeline_paths import DIR_INPUT, ensure_pipeline_subdirs, require_registered_pipeline_request
from pkg.data_plane.store import get_data_plane_store
from pkg.data_plane.types import DataType
from pkg.llm.overrides_store import database_path, load_overrides, save_overrides
from pkg.llm.prompt_store import DEFAULT_PROMPTS, build_system_for_chat, load_prompts, save_prompts
from application.mcp_resource_payload import mcp_tools_payload

ptagent_admin_router = APIRouter(prefix="/ptagent-admin", tags=["ptagent-admin"])


class AgentUpsertBody(BaseModel):
    key: str = Field(..., min_length=1)
    name: str = ""
    description: str = ""
    mcp_categories: list[str] | None = None
    mcp_tool_allowlist: list[str] | None = None
    system_prompt: str = ""
    rag_profile_id: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2
    interaction_mode: str = "freeform"
    meta: dict[str, Any] = Field(default_factory=dict)


class TeamUpsertBody(BaseModel):
    key: str = Field(..., min_length=1)
    name: str = ""
    linear_order: list[str] = Field(default_factory=list)
    graph: dict[str, Any] | None = None


class RunBody(BaseModel):
    """统一运行入口。"""

    target: Literal["agent", "team"]
    key: str = Field(..., min_length=1)
    task: str = "测试任务"
    model: str | None = None
    temperature: float | None = None
    data_payload: dict[str, Any] | None = None


class LlmSettingsPut(BaseModel):
    openai_api_base: str | None = None
    openai_api_key: str | None = None


class LlmModelConnectionPut(BaseModel):
    """Per-model OpenAI-compatible endpoint (stored under ``llm_overrides.model_connections``)."""

    model: str = Field(..., min_length=1)
    remove: bool = False
    openai_api_base: str | None = None
    openai_api_key: str | None = None


class LlmTestBody(BaseModel):
    model: str = "gpt-4o-mini"
    message: str = "ping"


class ChatMessageItem(BaseModel):
    role: str = "user"
    content: str = ""


class LlmChatMessagesBody(BaseModel):
    """Multi-turn chat for experiment / workflow planning (home UI)."""

    model: str = "gpt-4o-mini"
    messages: list[ChatMessageItem] = Field(default_factory=list)
    system: str | None = None
    """若为空则使用服务器 SQLite 中的 prompt（见 ``prompt_key``）。"""
    prompt_key: str = "guided_experiment"
    """``guided_experiment`` | ``spectrum_chat``；与 ``system`` 互斥（``system`` 优先）。"""
    max_tokens: int = 4096
    temperature: float = 0.3
    include_mcp_catalog: bool = True


class LlmPromptsPut(BaseModel):
    """更新 ``llm_prompts`` kv 中的若干键。"""

    prompts: dict[str, str] = Field(default_factory=dict)


class GraphLintBody(BaseModel):
    graph: dict[str, Any]


class SuggestPayloadBody(BaseModel):
    input_keys: list[str] = Field(default_factory=list)


def _sample_value_for_field(key: str, cat: dict[str, Any]) -> Any:
    builtins = {str(x.get("key")): x for x in cat.get("builtinFields") or [] if isinstance(x, dict)}
    convs = {str(x.get("key")): x for x in cat.get("conventionFields") or [] if isinstance(x, dict)}
    row = builtins.get(key) or convs.get(key)
    t = str((row or {}).get("json_schema_type") or "").lower()
    if "integer" in t:
        return 2
    if "number" in t:
        return 123.45
    if "array" in t:
        return [1, 2, 3]
    if "object" in t:
        return {}
    if key in ("peptide", "normalized_sequence", "peptide_with_ptm", "peptide_bare"):
        return "ACDEFGHIKLM"
    if key == "charge":
        return 2
    if key == "task":
        return "演示任务"
    return "sample"


@ptagent_admin_router.get("/api/overview")
def api_overview() -> dict[str, Any]:
    mcp = get_mcp_settings()
    store = get_registry_store()
    return {
        "mcpEndpoint": mcp.endpoint,
        "registryPath": str(store.path),
        "agentCount": len(store.list_agent_records()),
        "teamCount": len(store.list_team_records()),
    }


@ptagent_admin_router.get("/api/workflow-data-keys")
def api_workflow_data_keys() -> dict[str, Any]:
    """编排入口/出口勾选：内置 state.data 键 + ``config.mcp_conventions`` 中的 MCP 字段。"""
    return workflow_data_key_catalog()


@ptagent_admin_router.post("/api/graph/lint")
def api_graph_lint(body: GraphLintBody) -> dict[str, Any]:
    """校验 Team graph 结构；并返回多分叉并行时的提示。"""
    g = body.graph
    errs = validate_team_graph(g)
    warns = fork_warnings(g)
    return {"ok": len(errs) == 0, "errors": errs, "warnings": warns}


@ptagent_admin_router.post("/api/graph/suggest-data-payload")
def api_graph_suggest_data_payload(body: SuggestPayloadBody) -> dict[str, Any]:
    """根据入口键生成示例 ``data_payload``（供试运行 JSON 一键填充）。"""
    cat = workflow_data_key_catalog()
    keys = [str(x).strip() for x in body.input_keys if str(x).strip()]
    sample: dict[str, Any] = {}
    for k in keys:
        if k == "task":
            continue
        sample[k] = _sample_value_for_field(k, cat)
    return {
        "data_payload": sample,
        "note": "task 由试运行表单单独传入并写入 state.data；上表为约定字段示例。",
    }


@ptagent_admin_router.get("/api/mcp-resources")
def api_mcp_resources() -> dict[str, Any]:
    return mcp_tools_payload()


@ptagent_admin_router.get("/api/llm/settings")
def api_llm_settings_get() -> dict[str, Any]:
    out = get_openai_settings_for_ui(include_plaintext_key=True)
    out["databasePath"] = str(database_path())
    return out


@ptagent_admin_router.put("/api/llm/settings")
def api_llm_settings_put(body: LlmSettingsPut) -> dict[str, Any]:
    raw = body.model_dump(exclude_unset=True)
    ov = load_overrides()
    if "openai_api_base" in raw:
        b = raw["openai_api_base"]
        if b is None or (isinstance(b, str) and not str(b).strip()):
            ov.pop("openai_api_base", None)
        else:
            ov["openai_api_base"] = str(b).strip()
    if "openai_api_key" in raw:
        k = raw["openai_api_key"]
        if k is None or (isinstance(k, str) and not str(k).strip()):
            ov.pop("openai_api_key", None)
        else:
            ov["openai_api_key"] = str(k).strip()
    save_overrides(ov)
    return {"ok": True, "settings": get_openai_settings_for_ui(include_plaintext_key=True)}


@ptagent_admin_router.get("/api/llm/prompts")
def api_llm_prompts_get() -> dict[str, Any]:
    """当前生效的 UI 用 System Prompt（含默认值合并）。"""
    merged = load_prompts()
    return {
        "prompts": merged,
        "defaults": dict(DEFAULT_PROMPTS),
        "databasePath": str(database_path()),
    }


@ptagent_admin_router.put("/api/llm/prompts")
def api_llm_prompts_put(body: LlmPromptsPut) -> dict[str, Any]:
    """写入 Prompt 片段（SQLite ``llm_prompts``）。"""
    merged = save_prompts(dict(body.prompts))
    return {"ok": True, "prompts": merged}


@ptagent_admin_router.put("/api/llm/settings/model-connection")
def api_llm_model_connection_put(body: LlmModelConnectionPut) -> dict[str, Any]:
    """Save or clear per-model ``openai_api_base`` / ``openai_api_key`` (overrides global defaults)."""
    ov = load_overrides()
    mc: dict[str, Any] = dict(ov.get("model_connections") or {})
    mid = str(body.model).strip()
    if not mid:
        raise HTTPException(status_code=400, detail="model is required")
    if body.remove:
        mc.pop(mid, None)
    else:
        entry: dict[str, Any] = dict(mc.get(mid) or {})
        if body.openai_api_base is not None:
            b = str(body.openai_api_base).strip()
            if b:
                entry["openai_api_base"] = b
            else:
                entry.pop("openai_api_base", None)
        if body.openai_api_key is not None:
            k = str(body.openai_api_key).strip()
            if k:
                entry["openai_api_key"] = k
            else:
                entry.pop("openai_api_key", None)
        if entry:
            mc[mid] = entry
        else:
            mc.pop(mid, None)
    ov["model_connections"] = mc
    save_overrides(ov)
    return {"ok": True, "settings": get_openai_settings_for_ui(include_plaintext_key=True)}


@ptagent_admin_router.post("/api/llm/test")
def api_llm_test(body: LlmTestBody) -> dict[str, Any]:
    return test_openai_chat(model=body.model, user_message=body.message)


@ptagent_admin_router.post("/api/llm/chat")
def api_llm_chat_messages(body: LlmChatMessagesBody) -> dict[str, Any]:
    """Multi-turn chat completion (workflow planning)."""
    msgs = [{"role": m.role, "content": m.content} for m in body.messages]
    system = build_system_for_chat(
        prompt_key=body.prompt_key,
        system_override=body.system,
    )
    return chat_completion_messages(
        model=body.model,
        messages=msgs,
        system=system,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        include_mcp_catalog=body.include_mcp_catalog,
    )


@ptagent_admin_router.post("/api/llm/chat/stream")
def api_llm_chat_stream(body: LlmChatMessagesBody) -> StreamingResponse:
    """SSE stream of assistant tokens (``data: {\"t\":\"...\"}`` then ``data: {\"done\":true}``)."""
    import json

    msgs = [{"role": m.role, "content": m.content} for m in body.messages]
    system = build_system_for_chat(
        prompt_key=body.prompt_key,
        system_override=body.system,
    )

    def gen() -> Iterator[str]:
        acc = ""
        try:
            for piece in iter_chat_completion_messages_stream(
                model=body.model,
                messages=msgs,
                system=system,
                max_tokens=body.max_tokens,
                temperature=body.temperature,
                include_mcp_catalog=body.include_mcp_catalog,
            ):
                acc += piece
                yield f"data: {json.dumps({'t': piece}, ensure_ascii=False)}\n\n"
            # Many OpenAI-compatible proxies return an empty stream but a valid non-stream body.
            if not acc.strip():
                fb = chat_completion_messages(
                    model=body.model,
                    messages=msgs,
                    system=system,
                    max_tokens=body.max_tokens,
                    temperature=body.temperature,
                    include_mcp_catalog=body.include_mcp_catalog,
                )
                if fb.get("ok") and str(fb.get("reply") or "").strip():
                    reply = str(fb["reply"])
                    yield f"data: {json.dumps({'t': reply, 'nonstream_fallback': True}, ensure_ascii=False)}\n\n"
                elif not fb.get("ok"):
                    yield f"data: {json.dumps({'error': fb.get('error') or 'non-stream fallback failed'}, ensure_ascii=False)}\n\n"
                    return
                else:
                    yield f"data: {json.dumps({'error': 'Empty stream and empty non-stream reply (check model id, proxy streaming, max_tokens)'}, ensure_ascii=False)}\n\n"
                    return
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@ptagent_admin_router.post("/api/workflow/parse")
def api_workflow_parse(body: dict[str, Any]) -> dict[str, Any]:
    """Parse ```workflow`` JSON from model output text (server-side helper)."""
    text = str(body.get("text") or "")
    wf = parse_workflow_from_text(text)
    used_fb = False
    if wf is None and text.strip():
        wf = fallback_workflow_from_text(text)
        used_fb = True
    return {"workflow": wf, "ok": wf is not None, "fallback": used_fb}


@ptagent_admin_router.get("/api/experiment/examples")
def api_experiment_examples() -> dict[str, Any]:
    """Sample experiment fields + MGF + JSON spectrum for one-click fill."""
    mgf_path = project_root() / "data" / "samples" / "example.mgf"
    mgf_text = ""
    if mgf_path.is_file():
        mgf_text = mgf_path.read_text(encoding="utf-8")
    spectrum_json = {
        "Name": "ptagent_sample",
        "spectrum": [{"mz": 120.05, "intensity": 1500.0}, {"mz": 230.12, "intensity": 900.0}],
        "precursorMz": 500.2,
        "precursorCharge": 2,
    }
    return {
        "experiment": {
            "expName": "Demo — HeLa lysate DDA",
            "background": "Whole-cell lysate, tryptic digest, HCD MS/MS. Goal: QC + peptide ID workflow.",
            "instrument": "Orbitrap (Thermo)",
            "taxonId": "9606",
            "taxLabel": "Selected: Homo sapiens (taxonId 9606)",
        },
        "mgfText": mgf_text,
        "spectrumJson": spectrum_json,
    }


@ptagent_admin_router.get("/api/uniprot/taxonomy-common")
def api_uniprot_taxonomy_common() -> dict[str, Any]:
    """Curated common species for quick pick (NCBI taxon ids)."""
    results = [
        {"taxonId": 9606, "scientificName": "Homo sapiens", "commonName": "Human"},
        {"taxonId": 10090, "scientificName": "Mus musculus", "commonName": "Mouse"},
        {"taxonId": 10116, "scientificName": "Rattus norvegicus", "commonName": "Rat"},
        {"taxonId": 9913, "scientificName": "Bos taurus", "commonName": "Cattle"},
        {"taxonId": 9031, "scientificName": "Gallus gallus", "commonName": "Chicken"},
        {"taxonId": 7227, "scientificName": "Drosophila melanogaster", "commonName": "Fruit fly"},
        {"taxonId": 6239, "scientificName": "Caenorhabditis elegans", "commonName": "C. elegans"},
        {"taxonId": 4932, "scientificName": "Saccharomyces cerevisiae", "commonName": "Baker's yeast"},
        {"taxonId": 3702, "scientificName": "Arabidopsis thaliana", "commonName": "Thale cress"},
        {"taxonId": 8355, "scientificName": "Xenopus laevis", "commonName": "African clawed frog"},
        {"taxonId": 7955, "scientificName": "Danio rerio", "commonName": "Zebrafish"},
        {"taxonId": 9823, "scientificName": "Sus scrofa", "commonName": "Pig"},
    ]
    return {"results": results}


@ptagent_admin_router.get("/api/uniprot/taxonomy-search")
def api_uniprot_taxonomy_search(
    q: str = Query(..., min_length=1, description="Species / organism text"),
    limit: int = Query(10, ge=1, le=100),
) -> dict[str, Any]:
    """物种检索：经 MCP 调用 Broker 上已注册工具（默认 ``search_organism_taxonomy``）；失败则返回占位结果。"""
    return taxonomy_search_for_ui(q, limit=limit)


_MAX_UPLOAD_BYTES = 500 * 1024 * 1024
_ALLOWED_SPECTRUM_SUFFIXES = {".mgf", ".mzml", ".raw"}


class MgfTextBody(BaseModel):
    """Raw MGF text saved server-side for the same pipelines as file upload."""

    content: str = Field(..., min_length=1)


@ptagent_admin_router.post("/api/experiment/mgf-text")
def api_experiment_mgf_text(
    body: MgfTextBody,
    session_id: str | None = Query(
        None,
        description="可选；若提供须为已存在的 session_id，否则 400",
    ),
    request_id: str | None = Query(
        None,
        description="可选；若提供须已由 POST .../data-plane/pipeline-requests 登记，文件落至 data/pipelines/<id>/input/，并写入 DataObject.request_id",
    ),
) -> dict[str, Any]:
    """Persist pasted MGF as ``pasted.mgf`` under ``data/uploads/<uuid>/`` 或 pipeline ``input/<uuid>/``，并登记 :class:`DataObject`。"""
    raw = body.content
    n = len(raw.encode("utf-8"))
    if n > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Content too large (max 500MB)")
    uid = str(uuid.uuid4())
    safe = "pasted.mgf"
    if request_id:
        try:
            require_registered_pipeline_request(request_id, get_data_plane_store())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        dest_dir = (ensure_pipeline_subdirs(request_id) / DIR_INPUT / uid).resolve()
    else:
        dest_dir = (data_dir() / "uploads" / uid).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = (dest_dir / safe).resolve()
    if not str(dest).startswith(str(dest_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    dest.write_text(raw, encoding="utf-8")
    try:
        reg = register_file_as_data_object(
            dest,
            session_id=session_id,
            data_type=DataType.MGF,
            request_id=request_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    rel = (
        f"data/pipelines/{request_id}/input/{uid}/{safe}"
        if request_id
        else f"data/uploads/{uid}/{safe}"
    )
    out: dict[str, Any] = {
        "ok": True,
        "path": str(dest),
        "filename": safe,
        "uploadId": uid,
        "bytes": n,
        "relativePath": rel,
        "sessionId": reg["session_id"],
        "dataObjectId": reg["data_object_id"],
        "dataType": reg["data_type"],
    }
    if request_id is not None:
        out["requestId"] = request_id
    return out


@ptagent_admin_router.post("/api/experiment/upload")
async def api_experiment_upload(
    file: UploadFile = File(...),
    session_id: str | None = Query(
        None,
        description="可选；若提供须为已存在的 session_id",
    ),
    request_id: str | None = Query(
        None,
        description="可选；若提供须已登记于 pipeline-requests，文件落至 data/pipelines/<id>/input/，并写入 request_id",
    ),
) -> dict[str, Any]:
    """Store uploaded MGF / mzML / Thermo raw; 登记 DataObject，供 MCP 以 data_object_id 引用。"""
    raw_name = (file.filename or "spectrum").strip()
    safe = Path(raw_name).name
    suf = Path(safe).suffix.lower()
    if suf not in _ALLOWED_SPECTRUM_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported type {suf!r}; allowed: {sorted(_ALLOWED_SPECTRUM_SUFFIXES)}",
        )
    uid = str(uuid.uuid4())
    if request_id:
        try:
            require_registered_pipeline_request(request_id, get_data_plane_store())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        dest_dir = (ensure_pipeline_subdirs(request_id) / DIR_INPUT / uid).resolve()
    else:
        dest_dir = (data_dir() / "uploads" / uid).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = (dest_dir / safe).resolve()
    if not str(dest).startswith(str(dest_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename")
    total = 0
    try:
        with dest.open("wb") as buf:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File too large (max 500MB)")
                buf.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    try:
        reg = register_file_as_data_object(dest, session_id=session_id, request_id=request_id)
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    rel = (
        f"data/pipelines/{request_id}/input/{uid}/{safe}"
        if request_id
        else f"data/uploads/{uid}/{safe}"
    )
    out: dict[str, Any] = {
        "ok": True,
        "path": str(dest),
        "filename": safe,
        "uploadId": uid,
        "bytes": total,
        "relativePath": rel,
        "sessionId": reg["session_id"],
        "dataObjectId": reg["data_object_id"],
        "dataType": reg["data_type"],
    }
    if request_id is not None:
        out["requestId"] = request_id
    return out


@ptagent_admin_router.get("/api/llm/models")
def api_llm_models() -> dict[str, Any]:
    return {"models": list_chat_models_for_ui()}


@ptagent_admin_router.post("/api/llm/ping-all")
def api_llm_ping_all() -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    for m in list_chat_models_for_ui():
        mid = str(m.get("id") or "")
        if not mid:
            continue
        r = test_openai_chat(model=mid, user_message="ping")
        out.append({"id": mid, "label": m.get("label"), **r})
    return {"results": out}


@ptagent_admin_router.get("/api/agents")
def api_list_agents() -> dict[str, Any]:
    store = get_registry_store()
    return {"agents": list(store.list_agent_records().values())}


@ptagent_admin_router.get("/api/agents/{key}")
def api_get_agent(key: str) -> dict[str, Any]:
    store = get_registry_store()
    r = store.get_agent_record(key)
    if not r:
        raise HTTPException(status_code=404, detail="unknown agent")
    return {"agent": r}


@ptagent_admin_router.put("/api/agents/{key}")
def api_put_agent(key: str, body: AgentUpsertBody) -> dict[str, Any]:
    if body.key != key:
        raise HTTPException(status_code=400, detail="body.key 必须与路径 key 一致")
    store = get_registry_store()
    store.upsert_agent(body.model_dump())
    spec = record_to_agent_spec(body.model_dump())
    return {"ok": True, "agent": agent_spec_to_record(spec)}


@ptagent_admin_router.delete("/api/agents/{key}")
def api_delete_agent(key: str) -> dict[str, Any]:
    store = get_registry_store()
    if not store.delete_agent(key):
        raise HTTPException(status_code=404, detail="unknown agent")
    return {"ok": True}


@ptagent_admin_router.get("/api/teams")
def api_list_teams() -> dict[str, Any]:
    store = get_registry_store()
    return {"teams": list(store.list_team_records().values())}


@ptagent_admin_router.get("/api/teams/{key}")
def api_get_team(key: str) -> dict[str, Any]:
    store = get_registry_store()
    r = store.list_team_records().get(key)
    if not r:
        raise HTTPException(status_code=404, detail="unknown team")
    return {"team": r}


@ptagent_admin_router.put("/api/teams/{key}")
def api_put_team(key: str, body: TeamUpsertBody) -> dict[str, Any]:
    if body.key != key:
        raise HTTPException(status_code=400, detail="body.key 必须与路径 key 一致")
    store = get_registry_store()
    try:
        store.upsert_team(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "team": store.list_team_records()[key]}


@ptagent_admin_router.delete("/api/teams/{key}")
def api_delete_team(key: str) -> dict[str, Any]:
    store = get_registry_store()
    if not store.delete_team(key):
        raise HTTPException(status_code=404, detail="unknown team")
    return {"ok": True}


def _spec_map_from_store(store: Any) -> dict[str, AgentSpec]:
    return {k: record_to_agent_spec(v) for k, v in store.list_agent_records().items()}


@ptagent_admin_router.post("/api/run")
def api_run(body: RunBody) -> dict[str, Any]:
    store = get_registry_store()
    sm = _spec_map_from_store(store)
    if body.target == "agent":
        if not openai_api_configured():
            raise HTTPException(
                status_code=400,
                detail="未配置 OpenAI API Key：请在「LLM 设置」页填写，或设置环境变量 OPENAI_API_KEY。",
            )
        r = store.get_agent_record(body.key)
        if not r:
            raise HTTPException(status_code=404, detail="unknown agent")
        spec = record_to_agent_spec(r)
        return run_single_agent_graph(
            spec,
            task=body.task,
            model=body.model,
            temperature=body.temperature,
            run_id=f"run-agent-{body.key}",
        )
    tr = store.list_team_records().get(body.key)
    if not tr:
        raise HTTPException(status_code=404, detail="unknown team")
    team = record_to_team(tr)
    needs_llm = team_requires_llm(team)
    if needs_llm and not openai_api_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "未配置 OpenAI API Key：当前 Team 含 Agent 节点，需要 LLM。"
                " 请在「LLM 设置」中配置，或设置 OPENAI_API_KEY。"
                " 若编排仅含起点/工具/终点（无 Agent），可在无 Key 下试运行。"
            ),
        )
    try:
        graph = build_team_mcp_workflow(
            team,
            agent_specs_by_key=sm,
            llm=compile_llm_client() if needs_llm else None,
            model=body.model,
            temperature=body.temperature,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = run_invocation(
        graph,
        task=body.task,
        run_id=f"run-team-{body.key}",
        extra_data=body.data_payload,
    )
    return {"result": result}


@ptagent_admin_router.post("/api/agents/{key}/debug/validate")
def api_debug_validate_agent(key: str) -> dict[str, Any]:
    store = get_registry_store()
    r = store.get_agent_record(key)
    if not r:
        raise HTTPException(status_code=404, detail="unknown agent")
    spec = record_to_agent_spec(r)
    return validate_agent(spec)
