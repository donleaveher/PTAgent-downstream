# 脚本说明

项目根目录下的 **`scripts/`** 只保留少量入口，避免重复、错误路径或过时的模块名。

| 脚本 | 作用 |
|------|------|
| **`setup.sh`** | 用 `uv` 创建虚拟环境并 `pip install -r requirements.txt` |
| **`run-backend.sh`** | 启动 **FastAPI 后端**（`uvicorn main:app`，`PYTHONPATH=src`） |
| **`run-mcp-broker.sh`** | （可选）**单独**启动 MCP Broker；一般不需要，后端会在 `PTAGENT_MCP_SETTINGS__AUTO_START_SUBPROCESS=true` 时自动拉起 |
| **`run-mcp-tool-providers.sh`** | （可选）若已设置 **`PTAGENT_MCP_TOOL_ROOT`**（或兼容 **`PTAGENT_MCP_ROOT`**）指向**外部** MCP 工具仓库根目录，则**转调**该仓内的 `scripts/run-mcp-tool-providers.sh`。主仓不包含 Tool Provider 实现。 |

## 推荐：第一次运行

```bash
cd /path/to/PTAgent
cp .env.example .env   # 编辑 JWT、PTAGENT_MCP_SETTINGS__ENDPOINT 等
./scripts/setup.sh
source .venv/bin/activate   # 若使用 uv 默认 .venv；若用仓库已有 .venv-ProtAgent 则 source 该目录
./scripts/run-backend.sh
```

浏览器访问 API 文档：`http://localhost:8000/docs`；MCP 控制台：`http://localhost:8000/mcp-admin/`。

## 环境变量提示

- **`PORT`**：后端端口（`run-backend.sh` 默认 `8000`）。
- **`MCP_BROKER_HOST` / `MCP_BROKER_PORT`**：仅用于 `run-mcp-broker.sh`（默认 `0.0.0.0:8765`），需与 `.env` 里 `PTAGENT_MCP_SETTINGS__ENDPOINT` 一致。
- **`PTAGENT_MCP_TOOL_ROOT`**：外部 MCP Tool Provider 仓库根路径（兼容旧名 **`PTAGENT_MCP_ROOT`**），仅在使用 `run-mcp-tool-providers.sh` 时需要。

## 等效命令（不用脚本）

```bash
export PYTHONPATH=/path/to/PTAgent/src
cd /path/to/PTAgent
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
