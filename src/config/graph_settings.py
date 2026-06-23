"""Neo4j / 关系图谱连接配置。

嵌套在 :class:`config.settings.AppSettings` 的 ``graph`` 字段中加载;环境变量前缀为
``PTAGENT_GRAPH__``(例如 ``PTAGENT_GRAPH__URI``、``PTAGENT_GRAPH__PASSWORD``)。

业务代码若只关心图数据库,可用 :func:`get_graph_settings` 取当前 ``GraphSettings`` 实例
(供 ``pkg.graph.store.get_graph_store`` 使用)。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GraphSettings(BaseModel):
    """Neo4j 图数据库连接配置。"""

    uri: str = Field(
        "bolt://127.0.0.1:7687",
        description="Neo4j Bolt 连接地址,如 bolt://host:7687 或 neo4j://host:7687。",
    )
    user: str = Field("neo4j", description="Neo4j 用户名。")
    password: str = Field(
        "",
        description="Neo4j 密码(生产环境请用安全随机值,勿提交到仓库)。",
    )
    database: str = Field(
        "neo4j",
        description="Neo4j 数据库名(社区版固定为 neo4j;企业版可分库)。",
    )


def get_graph_settings() -> GraphSettings:
    """返回当前应用配置中的图数据库段(等价于 ``get_settings().graph``)。"""

    from .settings import get_settings

    return get_settings().graph


__all__ = ["GraphSettings", "get_graph_settings"]
