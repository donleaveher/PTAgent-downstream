# `mcp_tools.basic`

「basic」类目下包含**多个平级的工具子项目**，每个子项目自有目录，不在本层堆叠实现文件。

| 子项目 | 路径 | 说明 |
|--------|------|------|
| 肽段 | [`peptide/`](peptide/README.md) | MCP 3 工具：`normalize_peptide` / `peptide_mass_and_mz` / `tokens_to_peptide_strings` |

新增子项目时：在 `mcp_tools/basic/<name>/` 下建立 `core/`（纯逻辑）与可选 `provider.py`，并在本 README 表格中登记。
