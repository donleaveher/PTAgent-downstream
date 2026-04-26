# `config`：配置与环境管理

本目录主要用于管理项目在不同环境（本地开发 / 测试 / 生产）下的配置，包括：

- LLM / 向量库 / 质谱软件等外部服务的连接信息。
- 项目级别的默认参数（如默认数据库版本、物种、FDR 阈值等）。
- 日志级别、超时、重试策略等运行时参数。

## 建议做法

- 使用 **`.env` + Pydantic Settings** 的组合管理敏感配置与非敏感配置。
- 将敏感信息（API Key 等）只放在 `.env` / 环境变量中，不写入代码仓库。
- 使用统一的 `AppSettings` 类，在项目中通过依赖注入或单例方式访问配置。

## MCP 配置

- 模型定义见 **`mcp_settings.py`**（`MCPSettings`）：endpoint、mode、version、子进程相关等。
- 环境变量前缀为 **`PTAGENT_MCP_SETTINGS__`**（示例见仓库根目录 `.env.example`）。
- 业务代码若只需 MCP 一段，可 `from config import get_mcp_settings`（等价于 `get_settings().mcp_settings`）。

## TODO 列表

- [ ] **基础配置系统**
  - [ ] 定义 `AppSettings` / `LLMSettings` / `VectorStoreSettings` 等配置模型。
  - [ ] 支持从 `.env` / 环境变量 / 配置文件加载。
- [ ] **多环境支持**
  - [ ] 约定环境标识（如 `ENV=dev|staging|prod`）。
  - [ ] 为不同环境提供默认配置模板（如 `config.dev.example.env`）。
- [ ] **安全与合规**
  - [ ] 明确哪些配置可以写入仓库（如 example 文件），哪些必须通过环境变量注入。
  - [ ] 预留与企业级密钥管理系统（如 Vault、KMS）的集成点。

