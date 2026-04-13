# `mcp_tools.basic.peptide`

## 布局

| 路径 | 说明 |
|------|------|
| `core/` | 常量、解析、`BasicPeptideToolkit` |
| `provider.py` | MCP **3 个工具**（``@tool(..., category=..., group=...)`` 供 Admin 分组） |

## MCP 工具（3）

1. **normalize_peptide** — 全流程：规范 PTM、**token_ids**（词表整数）、残基和/中性质量、m/z  
2. **peptide_mass_and_mz** — 输入 **token_ids_with_ptm**（与 `normalize_peptide` 输出字段同名）  
3. **token_ids_to_peptide_strings** — 由下标拼展示用规范字符串，并给出 **token_ids_bare**  

跨工具字段命名见 **`config/mcp_conventions.py`**；Admin「字段约定」经 ``pkg.mcp`` 动态加载，与之同步。

## 导入

```python
from mcp_tools.basic.peptide import BasicPeptideToolkit, BasicPeptideToolProvider
```
