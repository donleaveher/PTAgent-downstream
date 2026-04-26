"""仓库根目录与数据目录解析（供持久化、日志等共用）。"""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """
    项目根目录（含 ``src/``、``data/`` 的那一层）。

    优先环境变量 ``PTAGENT_PROJECT_ROOT``（容器/多 cwd 部署时必设，指向可写卷）。
    否则按 ``src/config/paths.py`` 相对定位。
    """
    env = os.environ.get("PTAGENT_PROJECT_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    # src/config/paths.py -> parents[2] = repo root
    return here.parents[2]


def data_dir() -> Path:
    d = project_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d
