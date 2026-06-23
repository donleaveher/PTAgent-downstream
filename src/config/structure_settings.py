"""结构相似检索（Foldseek over AlphaFold DB）配置。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StructureSettings(BaseModel):
    """Foldseek 结构近邻检索的运行与筛选约定。"""

    foldseek_binary: str = Field("foldseek", min_length=1, description="foldseek 可执行文件名或路径。")
    alphafold_db: str = Field(
        "data/alphafold/afdb",
        min_length=1,
        description="预构建的 Foldseek 目标库（AlphaFold DB）路径。",
    )
    query_structure_dir: str = Field(
        "data/structures",
        min_length=1,
        description="本地查询结构（实验蛋白的 AlphaFold 模型）目录。",
    )
    top_k: int = Field(20, ge=1, le=1000, description="每个查询保留的结构近邻数量。")
    min_score: float = Field(0.0, ge=0.0, le=1.0, description="近邻 prob 阈值（结构相似度）。")
    min_coverage: float = Field(0.0, ge=0.0, le=1.0, description="近邻 tcov 覆盖度阈值。")
    exclude_self: bool = Field(True, description="是否剔除自身命中。")
    version: str = Field(
        "foldseek-unknown",
        min_length=1,
        description="Foldseek/AlphaFold DB 版本，写入 provenance。",
    )
    format_columns: tuple[str, ...] = Field(
        ("query", "target", "fident", "qcov", "tcov", "prob", "evalue", "bits", "taxid", "taxname"),
        description="foldseek --format-output 列序；解析端按同序读取。",
    )


__all__ = ["StructureSettings"]
