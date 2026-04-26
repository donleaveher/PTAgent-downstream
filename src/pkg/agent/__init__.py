"""
``pkg.agent``：可复用的 Agent 抽象、编排与 LangGraph 编译（执行内核）。

持久化记录、SQLite、``TeamSpec`` 与 Admin CRUD 见 ``application.agent``。

目录约定：
- ``core``：运行上下文与 Agent 抽象
- ``contracts``：``AgentSpec``、RAG 协议等纯约定
- ``workflow``：可组合工作流配置与编译（图结构）
- ``team``：MCP 绑定与多 Agent 构建
- ``validation``：Pipeline 静态校验
- ``_internal/``：LangGraph 细节、OpenAI 循环等，勿直接依赖
"""

from __future__ import annotations

from .contracts import AgentSpec, RAGRetriever, categories, null_rag
from .core import BaseAgent, RunContext
from .ports import LlmToolChatClient, ToolGateway
from .runner import compile_llm_client, run_invocation, run_single_agent_graph
from .team import (
    build_linear_mcp_team,
    build_mcp_workflow_graph,
    build_team_mcp_workflow,
    create_llm_mcp_agent,
    create_tool_llm_agent,
    invoke_linear_mcp_team,
)
from .team_spec import TeamSpec
from .validation import (
    PipelineValidationError,
    PipelineValidationIssue,
    PipelineValidationReport,
    check_pipeline_nodes,
    validate_pipeline_nodes,
)
from .workflow import WorkflowConfig, WorkflowNodeConfig, build_workflow_graph

__all__ = [
    "AgentSpec",
    "BaseAgent",
    "LlmToolChatClient",
    "RAGRetriever",
    "RunContext",
    "TeamSpec",
    "ToolGateway",
    "WorkflowConfig",
    "WorkflowNodeConfig",
    "build_linear_mcp_team",
    "build_mcp_workflow_graph",
    "build_team_mcp_workflow",
    "build_workflow_graph",
    "compile_llm_client",
    "categories",
    "check_pipeline_nodes",
    "create_llm_mcp_agent",
    "create_tool_llm_agent",
    "invoke_linear_mcp_team",
    "null_rag",
    "PipelineValidationError",
    "PipelineValidationIssue",
    "PipelineValidationReport",
    "run_invocation",
    "run_single_agent_graph",
    "validate_pipeline_nodes",
]
