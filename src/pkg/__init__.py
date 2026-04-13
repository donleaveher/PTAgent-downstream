"""
pkg 包：对外可复用的核心库接口。

约定：
- 外部/上层代码优先通过 pkg.* 引用核心能力，而不是直接引用内部实现细节。
"""

from .global_objects import GlobalObjects, close_global_objects, get_global_objects

__all__ = ["GlobalObjects", "get_global_objects", "close_global_objects"]

