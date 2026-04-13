# `mcp_tools`（位于 `src/mcp_tools`）

与 PTAgent 同仓；**仅需 `PYTHONPATH` 包含 `src`** 即可 `import mcp_tools` 与 `import pkg`。

## Admin 工具分组

在 Provider 里对 ``@tool`` 传入 ``category`` / ``group``（与 ``pkg.mcp.provider.tool`` 一致），随 **MCP 注册** 进入 Broker，经 ``Tool._meta`` 回到 Admin，**无需**单独维护 catalog JSON。

## `mcp_tools.basic`

按子项目组织，见 [`basic/README.md`](basic/README.md)。当前含肽段子项目 [`basic/peptide/`](basic/peptide/README.md)。

### 代码示例

```python
from mcp_tools.basic.peptide import BasicPeptideToolkit

tk = BasicPeptideToolkit()
print(tk.normalize_peptide_pipeline("AM(ox)K", charge=1))
```

### MCP Provider

```python
from config import get_mcp_settings
from mcp_tools.basic.peptide import BasicPeptideToolProvider

BasicPeptideToolProvider(get_mcp_settings().endpoint).run()
```

`ToolProvider` / ``tool`` 在 **`mcp_tools.basic.peptide.provider`** 中默认从 **`pkg.mcp.provider`** 直接导入；可选环境变量 **`MCP_TOOL_PROVIDER_MODULE`** 换其它模块。

### 一键启动 Provider

```bash
./scripts/run-mcp-tool-providers.sh
```

说明见 [`LAUNCH.md`](LAUNCH.md)。
