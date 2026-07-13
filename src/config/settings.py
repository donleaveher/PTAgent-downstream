from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .annotation_settings import AnnotationSettings
from .ctd_settings import CtdSettings
from .database_settings import DatabaseSettings, ExperimentDatabaseSettings
from .deep_search_settings import DeepSearchSettings
from .graph_settings import GraphSettings
from .mcp_settings import MCPSettings
from .structure_settings import StructureSettings


class AppEnv(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class JWTSettings(BaseModel):
    """JWT 相关配置。"""

    secret_key: str = Field(..., description="JWT 签名密钥")
    algorithm: str = Field("HS256", description="JWT 签名算法")
    issuer: str = Field("ProtAgent", description="JWT 发行方 iss，默认 ProtAgent")
    leeway_seconds: int = Field(60, description="时间误差容忍（秒）")


class AppSettings(BaseSettings):
    """应用全局配置，通过环境变量/`.env` 统一管理。"""

    model_config = SettingsConfigDict(
        env_prefix="PTAGENT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: AppEnv = Field(AppEnv.DEV, description="当前运行环境")

    api_version: str = Field("v1", description="对外 API 版本，对应 header 中的 apiVersion")

    jwt: JWTSettings
    mcp_settings: MCPSettings = Field(default_factory=MCPSettings)
    database: DatabaseSettings = Field(
        default_factory=DatabaseSettings,
        description="统一 SQLite（Agent、Team、LLM 覆盖与模型扩展）；默认 data/ptagent.db",
    )
    experiment_database: ExperimentDatabaseSettings = Field(
        default_factory=ExperimentDatabaseSettings,
        description="MySQL 实验事实库；环境变量前缀 PTAGENT_EXPERIMENT_DATABASE__",
    )
    annotation: AnnotationSettings = Field(
        default_factory=AnnotationSettings,
        description="下游蛋白基础注释；环境变量前缀 PTAGENT_ANNOTATION__",
    )
    ctd: CtdSettings = Field(
        default_factory=CtdSettings,
        description="CTD 基因-疾病直接证据；环境变量前缀 PTAGENT_CTD__",
    )
    deep_search: DeepSearchSettings = Field(
        default_factory=DeepSearchSettings,
        description="文献 deep-search MCP；环境变量前缀 PTAGENT_DEEP_SEARCH__",
    )
    structure: StructureSettings = Field(
        default_factory=StructureSettings,
        description="Foldseek 结构近邻检索；环境变量前缀 PTAGENT_STRUCTURE__",
    )
    graph: GraphSettings = Field(
        default_factory=GraphSettings,
        description="Neo4j 关系图谱连接；环境变量前缀 PTAGENT_GRAPH__",
    )

    # ===== LLM 相关配置（统一在此维护 URL 和鉴权） =====

    # OpenAI / 兼容 OpenAI 协议的服务（如企业代理）
    openai_api_base: Optional[str] = Field(
        default=None,
        description="OpenAI API Base URL，例如：https://api.openai.com/v1 或企业内部代理地址。",
    )
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API Key。若为空则退回使用环境变量 OPENAI_API_KEY。",
    )

    # Qwen（阿里百炼，兼容 OpenAI 协议）
    qwen_api_base: Optional[str] = Field(
        default=None,
        description="Qwen 兼容 OpenAI 协议的 base URL，例如：https://dashscope.aliyuncs.com/compatible-mode/v1。",
    )
    qwen_api_key: Optional[str] = Field(
        default=None,
        description="Qwen / 百炼 API Key。",
    )

    # DeepSeek（兼容 OpenAI 协议）
    deepseek_api_base: Optional[str] = Field(
        default=None,
        description="DeepSeek API base URL，例如：https://api.deepseek.com。",
    )
    deepseek_api_key: Optional[str] = Field(
        default=None,
        description="DeepSeek API Key。",
    )

    # HKUST GPT 代理（兼容 OpenAI 协议）
    hkust_gpt_api_base: Optional[str] = Field(
        default=None,
        description="HKUST GPT 代理的 base URL，例如：https://gpt-api.hkust-gz.edu.cn/v1。",
    )
    hkust_gpt_api_key: Optional[str] = Field(
        default=None,
        description="HKUST GPT 代理的 API Key（Bearer Token）。",
    )

    # GLM / 智谱
    glm_api_base: Optional[str] = Field(
        default=None,
        description="GLM / 智谱 API base URL（如使用官方 SDK 可留空）。",
    )
    glm_api_key: Optional[str] = Field(
        default=None,
        description="GLM / 智谱 API Key。",
    )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """获取全局唯一的 AppSettings 实例。"""

    return AppSettings()  # type: ignore[arg-type]
