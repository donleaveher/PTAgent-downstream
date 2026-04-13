# 脚本说明

项目根目录下的 **`scripts/`** 只保留少量入口，避免重复、错误路径或过时的模块名。

| 脚本 | 作用 |
|------|------|
| **`setup.sh`** | 用 `uv` 创建虚拟环境并 `pip install -r requirements.txt` |
| **`run-backend.sh`** | 启动 **FastAPI 后端**（`uvicorn main:app`，`PYTHONPATH=src`） |
| **`run-mcp-broker.sh`** | （可选）**单独**启动 MCP Broker；一般不需要，后端会在 `PTAGENT_MCP__AUTO_START_SUBPROCESS=true` 时自动拉起 |
| **`run-mcp-tool-providers.sh`** | **并行**启动 `mcp_tools` 里已注册的 Tool Provider（多进程连同一 Broker，**不额外占端口**） |

## 推荐：第一次运行

```bash
cd /path/to/PTAgent
cp .env.example .env   # 编辑 JWT、PTAGENT_MCP__ENDPOINT 等
./scripts/setup.sh
source .venv/bin/activate   # 若使用 uv 默认 .venv；若用仓库已有 .venv-ProtAgent 则 source 该目录
./scripts/run-backend.sh
```

浏览器访问 API 文档：`http://localhost:8000/docs`；MCP 控制台：`http://localhost:8000/mcp-admin/`。

## 环境变量提示

- **`PORT`**：后端端口（`run-backend.sh` 默认 `8000`）。
- **`MCP_BROKER_HOST` / `MCP_BROKER_PORT`**：仅用于 `run-mcp-broker.sh`（默认 `0.0.0.0:8765`），需与 `.env` 里 `PTAGENT_MCP__ENDPOINT` 一致。
- **`MCP_TOOLS_PROVIDERS`**：逗号分隔，控制 `run-mcp-tool-providers.sh` 拉起哪些 Provider（默认 `basic.peptide`，见 `src/mcp_tools/registry.py`）。
- **`MCP_TOOL_PROVIDER_MODULE`**：解析 `ToolProvider` / `tool` 的 Python 模块，默认 `pkg.mcp.provider`（见 `src/mcp_tools/basic/peptide/provider.py`）。

多进程 Provider 的端口与配置说明见 **`src/mcp_tools/LAUNCH.md`**。

## 等效命令（不用脚本）

```bash
export PYTHONPATH=/path/to/PTAgent/src
cd /path/to/PTAgent
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

`mcp_tools` 位于 **`src/mcp_tools`**，与 `pkg`、`config` 共用同一 `PYTHONPATH`。
