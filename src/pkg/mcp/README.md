# MCP（`pkg.mcp`）

## 对外三类能力

1. **`MCPService`** — 在本进程跑 Broker，或由主进程 `MCPService.ensure_subprocess` 拉起子进程。
2. **`MCPClient`** — `list_tools()` / `call_tool(name, args)`，仅走标准 MCP HTTP。
3. **`ToolProvider` + `@tool`** — 同事继承类、写方法、调用 `run()` 即可注册工具；协议与心跳在基类内处理。

实现细节在子包 **`pkg.mcp.mcp_framework`**，业务代码一般不必导入。

## Web 控制台（可视化 / 管理）

后端启动后访问 **`/mcp-admin/`**（或 **`/mcp-admin`**，会重定向到带斜杠地址）。多页界面源码在仓库 **`src/frontend/mcp/`**（概览 **`/`**、工具与参数 **`/tools`**、字段约定 **`/fields`**、调试 **`/debug`**），静态资源 **`/mcp-admin/static/`**，路由由 **`pkg/mcp/admin_router.py`** 注册到 FastAPI。

能力概览：

- 展示当前配置下的 endpoint、推导出的 HTTP MCP / Provider WS、模式与版本、Broker 是否可达、工具数量。
- 拉取并浏览工具列表及 JSON Schema（工具 **category / group** 来自注册时的 ``@tool``，经 MCP ``meta`` 展示）。
- 对任意工具发起一次 `tools/call` 测试（参数为 JSON 对象）。
- 点 **「填入示例参数」** 可为若干内置工具（如肽段三工具）填入可运行示例 JSON；失败时 HTTP 响应体会带上 **`detail`**（含 Provider 经 Broker 返回的具体错误文本）。
- **字段约定**：``GET /mcp-admin/api/conventions`` 由 :func:`pkg.mcp.conventions.load_conventions_document` 加载（默认 ``config.mcp_conventions``；``PTAGENT_MCP_CONVENTIONS_MODULE`` 可覆盖）。**工具分组**：由 Provider 在 ``@tool(description=..., category=..., group=...)`` 声明，Broker 写入 MCP ``Tool._meta.ptagent``；``GET /mcp-admin/api/tool-catalog`` 仅根据当前已注册工具推导摘要。业务数据不在 ``pkg`` 内硬编码。

生产环境请在网关或中间件侧限制该路径的访问，避免未授权调用 MCP 工具。

## 工具开发者示例

```python
from config import get_mcp_settings
from pkg.mcp import ToolProvider, tool

class MyTools(ToolProvider):
    provider_label = "my-team"

    @tool(description="示例加法", category="demo", group="demo.math")
    def add(self, a: int, b: int) -> dict:
        return {"sum": a + b}

if __name__ == "__main__":
    MyTools(get_mcp_settings().endpoint).run()
```

更完整说明见 `mcp_framework/README.md`。

肽段等工具包见 **`src/mcp_tools/`**（`PYTHONPATH` 含 `src` 即可；若需 `ToolProvider` 接入 Broker，见 `src/mcp_tools/README.md`）。
