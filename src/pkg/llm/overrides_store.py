"""本地覆盖 OpenAI 兼容端点（写入 ``data/llm_overrides.json``，优先于环境变量中的 PTAGENT_ 配置）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def overrides_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    d = root / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "llm_overrides.json"


def load_overrides() -> dict[str, Any]:
    p = overrides_path()
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_overrides(data: dict[str, Any]) -> None:
    p = overrides_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
