"""
pkg 包：**可复用**核心库（与 HTTP 路由、具体产品页面解耦）。

约定：
- ``router`` / ``application`` 通过 ``pkg.*`` 调用领域与基础设施能力。
- 勿在 ``pkg`` 中放入仅某条 Admin API、某页面专用的编排；见仓库根目录 ``docs/ARCHITECTURE.md``。
"""

from .global_objects import GlobalObjects, close_global_objects, get_global_objects

__all__ = ["GlobalObjects", "get_global_objects", "close_global_objects"]

