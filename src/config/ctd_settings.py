"""CTD 基因-疾病直接证据配置。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CtdSettings(BaseModel):
    """CTD genes-diseases 文件的读取与直接证据过滤约定。"""

    data_file: str = Field(
        "data/ctd/CTD_genes_diseases.csv",
        min_length=1,
        description="CTD genes-diseases 导出文件路径（相对 PTAGENT_PROJECT_ROOT 或绝对路径）。",
    )
    version: str = Field(
        "CTD-unknown",
        min_length=1,
        description="CTD 数据版本（下载批次/日期），写入 provenance。",
    )
    direct_evidence_types: tuple[str, ...] = Field(
        ("marker/mechanism", "therapeutic"),
        description="允许作为结论级直接证据的 DirectEvidence 取值；其余（含纯化学物推断）排除。",
    )


__all__ = ["CtdSettings"]
