# MCP（`pkg.mcp`）

## 对外三类能力

1. **`MCPService`** — 在本进程跑 Broker，或由主进程 `MCPService.ensure_subprocess` 拉起子进程。
2. **`MCPClient`** — `list_tools()` / `call_tool(name, args)`，仅走标准 MCP HTTP。
3. **`ToolProvider` + `@tool`** — 同事继承类、写方法、调用 `run()` 即可注册工具；协议与心跳在基类内处理。

实现细节在子包 **`pkg.mcp.core`**，业务代码一般不必导入。

## Web 控制台（可视化 / 管理）

**HTML/静态** 由 **`PTAgent-frontend/edge` 独立进程** 在默认端口 `8080` 提供，与 FastAPI 解耦；**API** 为 **`/mcp-admin/api/...`**（`router/mcp_admin.py`）。多页 UI 源文件在 `PTAgent-frontend/frontend/mcp/`。示例参数读写见 **`application/mcp_tool_arg_presets.py`**。

能力概览：

- 展示当前配置下的 endpoint、推导出的 HTTP MCP / Provider WS、模式与版本、Broker 是否可达、工具数量。
- 进入 **「工具与参数」** 页会自动拉取工具列表及 JSON Schema（工具 **category / group** 来自注册时的 ``@tool``，经 MCP ``meta`` 展示）。
- 对任意工具发起一次 `tools/call` 测试（参数为 JSON 对象）。
- **示例参数**：仅存 SQLite（``kv.mcp_tool_arg_presets``），**无自动导入**，空库即空。工具表展示「示例参数」列；``GET/PUT /mcp-admin/api/tool-arg-presets``、``POST .../item`` 供保存。工具返回若缺少 ``structuredContent``，客户端会将 **content 文本** 解析为 JSON 或包装为 ``rawText``，避免结果区空白（见 ``pkg/mcp/client.py``）。
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

更完整说明见 `pkg.mcp.core/README.md`。

业务侧 Tool Provider 可在**任意独立仓库**实现并接入同一 Broker；本仓仅提供 `ToolProvider` 基类（`pkg.mcp`）与控制台。
