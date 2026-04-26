"""统一 SQLite 数据文件配置（Agent、Team、LLM 覆盖与模型扩展）。"""

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
