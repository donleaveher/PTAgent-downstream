"""PTAgent 管理：运行 API + MCP 资源 + Agent/Team CRUD + 静态 UI。"""

from __future__ import annotations

import mimetypes
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from config import get_mcp_settings
from config.mcp_conventions import workflow_data_key_catalog
from frontend.paths import PTAGENT
from pkg.agent.contracts import AgentSpec
from pkg.agent.debug_support import validate_agent
from pkg.agent.registry import (
    agent_spec_to_record,
    get_registry_store,
    record_to_agent_spec,
    record_to_team,
)
from pkg.agent.runner import compile_llm_client, run_invocation, run_single_agent_graph
from pkg.agent._internal.team_graph import fork_warnings, validate_team_graph
from pkg.agent.team import build_team_mcp_workflow, team_requires_llm
from pkg.llm.model_catalog import list_chat_models_for_ui
from pkg.llm.openai_runtime import get_openai_settings_for_ui, openai_api_configured, test_openai_chat
from pkg.llm.overrides_store import load_overrides, overrides_path, save_overrides
from pkg.mcp.resource_payload import mcp_tools_payload

_ROOT = PTAGENT
_ASSETS = (_ROOT / "assets").resolve()

ptagent_admin_router = APIRouter(prefix="/ptagent-admin", tags=["ptagent-admin"])


def _html(name: str) -> FileResponse:
    path = (_ROOT / name).resolve()
    root = _ROOT.resolve()
    if not path.is_file() or not str(path).startswith(str(root)):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="text/html; charset=utf-8")


def _static(rel: str) -> FileResponse:
    if ".." in rel or rel.startswith("/"):
        raise HTTPException(status_code=404)
    target = (_ASSETS / rel).resolve()
    if not str(target).startswith(str(_ASSETS)) or not target.is_file():
        raise HTTPException(status_code=404)
    media = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media)


@ptagent_admin_router.get("", include_in_schema=False)
def ptagent_slash() -> RedirectResponse:
    return RedirectResponse(url="/ptagent-admin/", status_code=307)


@ptagent_admin_router.get("/", response_class=HTMLResponse, include_in_schema=False)
def ptagent_dashboard() -> FileResponse:
    return _html("index.html")


@ptagent_admin_router.get("/agents", response_class=HTMLResponse, include_in_schema=False)
def ptagent_agents_page() -> FileResponse:
    return _html("agents.html")


@ptagent_admin_router.get("/flow", response_class=HTMLResponse, include_in_schema=False)
def ptagent_flow_page() -> FileResponse:
    return _html("flow.html")


@ptagent_admin_router.get("/llm", response_class=HTMLResponse, include_in_schema=False)
def ptagent_llm_page() -> FileResponse:
    return _html("llm.html")


@ptagent_admin_router.get("/static/{path:path}", include_in_schema=False)
def ptagent_static(path: str) -> FileResponse:
    return _static(path)


# --- API ---


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


class LlmTestBody(BaseModel):
    model: str = "gpt-4o-mini"
    message: str = "ping"


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
    out["overridesPath"] = str(overrides_path())
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


@ptagent_admin_router.post("/api/llm/test")
def api_llm_test(body: LlmTestBody) -> dict[str, Any]:
    return test_openai_chat(model=body.model, user_message=body.message)


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
