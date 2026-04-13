# MCP Tool Provider 启动与配置

包路径：**`src/mcp_tools`**。运行前：

```bash
export PYTHONPATH=/path/to/PTAgent/src
```

## 端口与进程

| 组件 | 监听端口 | 说明 |
|------|-----------|------|
| MCP Broker | 是 | HTTP MCP + Provider WebSocket |
| Tool Provider | 否 | WS **客户端** 连 Broker |

环境变量：`PTAGENT_MCP__ENDPOINT`、`MCP_TOOLS_PROVIDERS`、`MCP_TOOL_PROVIDER_MODULE`（见仓库根 `.env.example`）。
