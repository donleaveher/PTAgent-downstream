from __future__ import annotations

"""
pipeline 相关的 DTO / ViewModel。

说明：
- 这些模型用于 HTTP / Application 层之间传递“pipeline 生成”相关的数据；
- 不负责执行，只描述 pipeline 的结构。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


@dataclass
class PipelineNodeModel:
    """
    单个 Pipeline 节点的模型（LangGraph 友好）。

    - key：节点唯一标识（对应 WorkflowNodeConfig.key）
    - type：节点类型（如 ingest / analyze / report，或具体 agent 名称）
    - params：与节点相关的配置参数（由上层自由约定）
    - next_keys：顺序流向（下游节点 key 列表），对应 WorkflowNodeConfig.next_keys
    - condition_key：可选条件函数标识，对应 WorkflowNodeConfig.condition
    - conditional_branches：条件值到下游节点 key 的映射，
      对应 WorkflowNodeConfig.conditional_branches
    """

    key: str
    type: str
    params: Mapping[str, Any] = field(default_factory=dict)
    next_keys: List[str] = field(default_factory=list)
    condition_key: Optional[str] = None
    conditional_branches: Dict[str, str] = field(default_factory=dict)


@dataclass
class PipelineDefinitionModel:
    """
    完整 Pipeline 定义模型（仅用于“生成”，不负责执行）。

    该模型可以被转换为 pkg.agent.WorkflowConfig / WorkflowNodeConfig，
    再由 LangGraph 执行。
    """

    pipeline_id: str
    name: str
    entry_key: str
    nodes: List[PipelineNodeModel]
    meta: Dict[str, Any] = field(default_factory=dict)


__all__ = [
    "PipelineNodeModel",
    "PipelineDefinitionModel",
]


