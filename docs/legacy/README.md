# legacy/ · 旧框架归档（已作废，勿作设计依据）

> 这里的文档都是 **2026-06 师兄两轮反馈之前** 的旧框架产物，**已被推翻**。
> 仅作**历史参考**保留，避免污染当前设计。新框架以上一级目录为准：
> - [`../PROJECT-STATUS.md`](../PROJECT-STATUS.md) — 交接总览（唯一入口）
> - [`../scope-reframing-analysis.md`](../scope-reframing-analysis.md) — 逐条范围重构分析
> - [`../architecture.svg`](../architecture.svg) / [`../evidence-model.svg`](../evidence-model.svg) — 新架构图

## 为什么作废（旧 vs 新）

| 旧框架（本目录） | 新框架（已生效） |
|---|---|
| 起点 = 谱图 / de novo（"谱图进、报告出"闭环） | 起点 = **已鉴定的肽/蛋白 + 背景**（上游无感知·给定） |
| 知识不入图、只在线查 | **建多个通用知识图谱**（疾病/免疫/物种…）+ 本次实验图谱 |
| KNN = 序列相似（`gds.knn` 找相似肽） | KNN = **结构相似**（Foldseek over AlphaFold DB），跨物种天然桥接 |
| 定量/差异降级为可选 | **差异（case/control）是核心** |
| 上游鉴定（Casanovo/查库/novelty/蛋白推断）属本项目 | 上游**出范围**（师兄/他人负责） |

## 文件清单

| 文件 | 旧内容 | 作废原因 |
|---|---|---|
| `architecture-closed-loop.svg` | "谱图→肽→蛋白→序列KNN→假说→deep-search→报告"闭环 | 起点、KNN、知识不入图全推翻 |
| `architecture-data-pipeline.svg` | A 路(鉴定) / B 路(增强) 双数据通路 | A 路属上游，出范围 |
| `architecture-graph-schema.svg` | 实测关系图谱 schema（TrunkRow 等） | schema 重构为"通用KG+本次KG+evidence_level" |
| `materializer-dataflow.md` | materializer 把 run 产物解包进图的参数流 | materializer 属上游，出范围 |
| `pipeline-steps.svg` / `pipeline-steps-detail.md` / `.pdf` | 旧 10 步流程分镜（含上游 ②③④⑤） | 含已出范围的上游步骤 |
| `project-spec.md` | 早期规格 | §2/§4/§7+ 已作废，待按新框架重写 |
| `quant-data-location.svg` | 旧图 schema 里定量数据落点（TrunkRow/QuantRow） | 绑定旧图 schema |
| `storage-tiers-lookup.svg` | 旧数据平面分层（SQLite tiers） | 旧数据平面，已升 MySQL |
| `relational-graph-design.html` | 早期关系图谱设计 | 历史参考 |
| `remaining-work.md` | 旧框架剩余工作（A路/B路/定量/Neo4j GDS） | 整篇基于旧框架 |
| `phd-confirmation-checklist.html` / `.pdf` | 与师兄确认清单（de novo/DDA-DIA/Casanovo/GDS） | 确认项多属上游，已出范围 |
