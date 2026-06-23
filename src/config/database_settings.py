"""SQLite 基础设施库与 MySQL 实验事实库配置。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class DatabaseSettings(BaseModel):
    """
    单库持久化；环境变量前缀 ``PTAGENT_DATABASE__``（嵌套在 AppSettings 的 ``database`` 下）。

    默认 ``data/ptagent.db``（相对路径相对 ``PTAGENT_PROJECT_ROOT``）。
    """

    sqlite_path: Optional[str] = Field(
        None,
        description="SQLite 文件路径；默认 data/ptagent.db",
    )


class ExperimentDatabaseSettings(BaseModel):
    """下游实验事实库；与现有 SQLite 会话/Run 基础设施并行。"""

    host: str = Field("127.0.0.1", description="MySQL 主机。")
    port: int = Field(3306, ge=1, le=65535, description="MySQL 端口。")
    user: str = Field("ptagent", description="MySQL 用户名。")
    password: str = Field("", description="MySQL 密码，禁止提交真实值。")
    database: str = Field("ptagent_experiment", min_length=1, description="实验事实库名。")
    charset: str = Field("utf8mb4", description="连接字符集。")
    connect_timeout_seconds: int = Field(10, ge=1, description="连接超时秒数。")


def resolve_database_path() -> Path:
    """解析当前应使用的 SQLite 文件路径。"""
    from config import get_settings
    from config.paths import data_dir, project_root

    ds = get_settings().database
    root = project_root()
    raw = ds.sqlite_path
    if raw and str(raw).strip():
        p = Path(str(raw).strip())
        return p if p.is_absolute() else (root / p)
    return data_dir() / "ptagent.db"


__all__ = ["DatabaseSettings", "ExperimentDatabaseSettings", "resolve_database_path"]
