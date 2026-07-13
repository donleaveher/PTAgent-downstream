# 脚本说明

项目根目录下的 **`scripts/`** 只保留少量入口，避免重复、错误路径或过时的模块名。

| 脚本 | 作用 |
|------|------|
| **`setup.sh`** | 用 `uv` 创建虚拟环境并 `pip install -r requirements.txt` |
| **`run-backend.sh`** | 启动 **FastAPI 后端**（`uvicorn main:app`，`PYTHONPATH=src`） |
| **`run-mcp-broker.sh`** | （可选）**单独**启动 MCP Broker；一般不需要，后端会在 `PTAGENT_MCP_SETTINGS__AUTO_START_SUBPROCESS=true` 时自动拉起 |
| **`run-mcp-tool-providers.sh`** | （可选）若已设置 **`PTAGENT_MCP_TOOL_ROOT`**（或兼容 **`PTAGENT_MCP_ROOT`**）指向**外部** MCP 工具仓库根目录，则**转调**该仓内的 `scripts/run-mcp-tool-providers.sh`。主仓不包含 Tool Provider 实现。 |
| **`setup-pubmed-mcp.sh`** | 下载固定的 PubMed MCP v2.9.8 源码到运行时目录，供 Docker Compose 构建本项目下游文献服务。 |

## Smoke Tests

- **`smoke/deep_search_fixture_mysql_smoke.py`**：使用真实 MySQL 与本地文献 fixture，
  验证 deep-search 证据行、裁决历史引用、freeze manifest 和报告证据章节。它不调用真实文献
  MCP，输出仅是测试数据。
- **`smoke/deep_search_mcp_smoke.py`**：只读调用已配置的真实文献 MCP，验证
  `pubmed_search_articles`（或 `PTAGENT_DEEP_SEARCH__MCP_TOOL` 指定工具）的连通性和
  返回 schema；不写 MySQL。
- **`smoke/foldseek_sequence_domain_hypothesis_real_smoke.py --include-deep-search`**：
  在隔离 MySQL 实验中运行真实 Foldseek、序列/域融合、CTD 假说、KG 投影和真实
  PubMed deep-search，随后冻结并生成报告。默认使用内存图；附加 `--graph-store neo4j`
  使用已配置的真实 Neo4j，并在退出时清理该实验工作区（`--keep-neo4j-workspace` 可保留）。
  它使用静态 gene mapping，不依赖真实 UniProt MCP。附加 `--expect-candidate-fallback` 会断言指定候选基因和疾病的
  PubMed 回退证据已写入 MySQL，并逐条保存在冻结快照中；该模式需同时使用
  `--include-deep-search`。
- **`smoke/neo4j_kg_mysql_smoke.py`**：以真实 MySQL 和 Neo4j 验证 KG 投影、图遍历、
  幂等重投影和实验工作区隔离清理。运行说明见
  [`docs/neo4j-smoke.md`](../docs/neo4j-smoke.md)。

## Neo4j Maintenance

- `maintenance/neo4j_orphan_cleanup.py`：列出无引用的 smoke GENERAL 节点；默认 dry-run，
  只有 `--apply` 才删除列出的节点。
- `maintenance/rebuild_neo4j_v2.py --experiment-id EXP_ID`：从 MySQL 计算 schema-v2
  重建计划、图 checksum 及其与冻结快照的一致性；默认不修改 Neo4j。`--apply` 才写入；
  整图清空还需同时提供 `--reset-graph --confirm-reset RESET_NEO4J_V2`。

## PubMed MCP

该服务是下游文献召回服务，不需要 MCP Broker 或外部 Provider 仓。首次使用依次运行：

```bash
./scripts/setup-pubmed-mcp.sh
docker compose up -d --build pubmed-mcp
PYTHONPATH=src .venv/bin/python scripts/smoke/deep_search_mcp_smoke.py
```

第二条命令会构建容器并访问 PubMed/Europe PMC；第三条只读检索，不写 MySQL。

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
