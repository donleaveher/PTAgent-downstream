from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


@dataclass
class RunContext:
    """
    领域层的运行上下文实体。

    说明：
    - 表示一次完整分析任务/会话的元信息与配置；
    - 被注入到每个 Agent，用于访问项目级/样本级元信息与配置；
    - 不依赖具体框架（LangGraph/FastAPI），属于纯领域模型。
    """

    run_id: str

    # 请求级元信息（来自 HTTP headers 或调用方）
    request_id: Optional[str] = None
    api_version: Optional[str] = None
    mcp_version: Optional[str] = None
    mcp_mode: Optional[str] = None

    # 业务主体信息
    project_id: Optional[str] = None
    sample_id: Optional[str] = None
    user_id: Optional[str] = None

    # 业务相关配置（如 FDR 阈值、定量策略、数据库版本等）
    config: Mapping[str, Any] = field(default_factory=dict)

    # 预留给 RAG 或其他全局资源的上下文
    extra: Dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """
    所有业务 Agent 的抽象基类。

    设计要点：
    - 与 LangGraph 解耦：Agent 只关心输入/输出和上下文，不关心图的实现细节。
    - 便于被挂载到不同 Graph（顺序/并行/条件分支等）。
    """

    name: str
    description: str = ""

    def __init__(self, name: Optional[str] = None, description: str = "") -> None:
        if name is not None:
            self.name = name
        elif not hasattr(self, "name"):
            self.name = self.__class__.__name__
        if description:
            self.description = description

    @abstractmethod
    def run(self, context: RunContext, state: Mapping[str, Any]) -> Dict[str, Any]:
        """执行业务逻辑，返回写回 LangGraph state 的增量字典。"""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
