"""tool_name → 装载器（build_rows）。"""
from collections.abc import Callable
from application.graph.loaders import casanovo
from pkg.data_plane.store import DataPlaneStore
from pkg.graph.types import TrunkRow

Loader = Callable[[DataPlaneStore, dict], list[TrunkRow]]

# 一个 loader 可登记多个别名，覆盖工具实际可能的命名
_REGISTRY: dict[str, Loader] = {
    "casanovo": casanovo.build_rows,
    "casanovo_sequence": casanovo.build_rows,
}

def get_loader(tool_name: str) -> Loader | None:
    name = (tool_name or "").lower()
    if name in _REGISTRY:
        return _REGISTRY[name]
    # 兜底：按子串匹配，扛住 relay 前缀 / 命名空间（如 "mcp.casanovo.sequence"）
    for key, fn in _REGISTRY.items():
        if key in name:
            return fn
    return None