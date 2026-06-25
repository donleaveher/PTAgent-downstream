# 下游知识层 · 输入契约（上游 → 下游）

> **用途**：给上游（鉴定侧）一份明确的"交什么、怎么交"。上游**不传文件**（决策 Q7），
> 直接把**结构化的已鉴定结果 + 实验背景**递给下游。本契约即 `ExperimentBundle` 的字段规范，
> 文末示例已用真实模型 `pkg.experiment.ExperimentBundle` 校验通过（含跨表引用校验）。
> **定量（差异分析输入）走单独入口，见 §6。**
> **更新日期**：2026-06-25。

## 1. 怎么交

- **接口**：`POST /ptagent/api/experiments`，请求体 = 下面的 JSON（`Content-Type: application/json`）。
- **下游做什么**：校验 → 落库（`ExperimentBundle` → MySQL），返回 `experiment_id`。校验失败返回 `422`。
- **下游不做**：不解析任何文件（CSV/TSV/mzTab），不做谱图鉴定 / 查库归属 / 蛋白推断 / novelty。这些都在上游完成。

## 2. 顶层结构

```
{
  "context":  { … },          # 实验背景（1 个对象）
  "groups":   [ … ],          # 分组（≥1，必须含 case/control 各一类用于差异）
  "proteins": [ … ],          # 已鉴定蛋白（≥1，必填）
  "peptides": [ … ]           # 已鉴定肽段（可选，可空；建议提供作为证据）
}
```

## 3. 字段规范

> **重要**：模型为 **strict（`extra="forbid"`）—— 不认识的顶层字段会被拒绝**。
> 额外/自定义信息一律放进各对象的 `meta`（自由 dict），不要新增顶层键。

### 3.1 `context`（实验背景）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `experiment_id` | string | 建议 | 实验稳定 ID；省略则下游自动生成 `exp_<hex>`。**建议上游给稳定值**，便于后续引用。 |
| `title` | string | 否 | 标题 |
| `raw_text` | string | 否 | 背景/假设原文（下游据此理解疾病/通路等） |
| `disease` | string[] | 否 | 疾病名，如 `["Brain Ischemia"]` |
| `pathway` | string[] | 否 | 通路名 |
| `organism` | string | 否 | 物种名，如 `"Rattus norvegicus"` |
| `taxon_id` | int(>0) | 否 | NCBI taxon，如大鼠 `10116`、人 `9606` |
| `assay` | string | 否 | 实验类型，如 `"DIA-LC-MS/MS"` |
| `meta` 等 | — | 否 | 其余自定义放 `design`(dict) 或各处 `meta` |

### 3.2 `groups[]`（分组）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `group_id` | string | ✅ | 分组稳定 ID（组内唯一） |
| `label` | string | ✅ | 分组标签（**唯一**；肽段用 `group_label` 引用它） |
| `role` | enum | ✅ | `"case"` 或 `"control"`（差异分析按 role 选组） |
| `meta` | dict | 否 | 自定义 |

### 3.3 `proteins[]`（已鉴定蛋白）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `protein_id` | string | ✅ | 蛋白稳定 ID（实验内唯一；肽段用它引用蛋白） |
| `accession` | string | ✅ | UniProt accession，如 `"P52631"`（下游据此查 UniProt/结构） |
| `gene` | string | ✅ | 基因符号，如 `"Stat3"`（下游据此查 CTD 疾病） |
| `organism` | string | 否 | 物种 |
| `taxon_id` | int(>0) | 否 | NCBI taxon |
| `peptide_ids` | string[] | 否 | 该蛋白拥有的肽 `peptide_id` 列表（必须与 `peptides[]` 对应且归属一致） |
| `meta` | dict | 否 | 自定义 |

### 3.4 `peptides[]`（已鉴定肽段，可选）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `peptide_id` | string | ✅ | 肽段稳定 ID（实验内唯一） |
| `peptidoform` | string | ✅ | 带修饰的肽形式，如 `"DIIDSGVSC(+57.02)IK"` |
| `stripped_sequence` | string | ✅ | 裸序列（无修饰），如 `"DIIDSGVSCIK"` |
| `protein_id` | string | ✅ | 所属蛋白的 `protein_id`（必须存在于 `proteins[]`） |
| `confidence` | float[0,1] | ✅ | 鉴定置信度 |
| `group_label` | string | ✅ | 所属分组的 `label`（必须存在于 `groups[]`） |
| `spectrum_ids` | string[] | 否 | 谱图引用（仅溯源，下游不处理谱图） |
| `abundance` | float\|null | 否 | 肽段丰度 |
| `meta` | dict | 否 | 自定义 |

## 4. 跨表引用规则（校验会强制）

1. `group_id` / `group label` / `protein_id` / `peptide_id` **各自唯一**。
2. 每个 `peptide.group_label` 必须是某个 `group.label`。
3. 每个 `peptide.protein_id` 必须是某个 `protein.protein_id`。
4. 每个 `protein.peptide_ids` 里的 id 必须存在于 `peptides[]`，**且该肽的 `protein_id` 必须指回这个蛋白**（归属一致）。
5. 至少 1 个 `group`、至少 1 个 `protein`；`peptides` 可为空。

任一不满足 → `422`，响应里给出错误位置。

## 5. 完整示例（已通过真实模型校验）

```json
{
  "context": {
    "experiment_id": "exp_ciri_001",
    "title": "Jak2 在脑缺血再灌注损伤(CIRI)中的作用",
    "raw_text": "大鼠 MCAO 模型 vs 假手术；研究 Jak2/STAT3 通路在 CIRI 中的差异表达。",
    "disease": ["Brain Ischemia"],
    "pathway": ["JAK-STAT signaling"],
    "organism": "Rattus norvegicus",
    "taxon_id": 10116,
    "assay": "DIA-LC-MS/MS"
  },
  "groups": [
    {"group_id": "g_case", "label": "MCAO", "role": "case"},
    {"group_id": "g_ctrl", "label": "Sham", "role": "control"}
  ],
  "proteins": [
    {"protein_id": "prot_1", "accession": "P52631", "gene": "Stat3",
     "organism": "Rattus norvegicus", "taxon_id": 10116, "peptide_ids": ["pep_1"]},
    {"protein_id": "prot_2", "accession": "P55211", "gene": "Casp3",
     "organism": "Rattus norvegicus", "taxon_id": 10116, "peptide_ids": ["pep_2"]}
  ],
  "peptides": [
    {"peptide_id": "pep_1", "peptidoform": "VAVLDSPSSWLR", "stripped_sequence": "VAVLDSPSSWLR",
     "protein_id": "prot_1", "confidence": 0.99, "group_label": "MCAO",
     "abundance": 12500.0, "spectrum_ids": ["scan=1024"]},
    {"peptide_id": "pep_2", "peptidoform": "DIIDSGVSC(+57.02)IK", "stripped_sequence": "DIIDSGVSCIK",
     "protein_id": "prot_2", "confidence": 0.97, "group_label": "Sham", "abundance": 8300.0}
  ]
}
```

最小可接受体（无肽段）：`context` + 至少 1 个 `group` + 至少 1 个 `protein`（蛋白 `peptide_ids` 留空）。

## 6. 差异定量（下游自定义契约 · 单独入口）

bundle（§2–§5）覆盖**定性输入**（蛋白/肽/分组/背景）。**L2 蛋白级差异分析**还需要**定量数据**
（`蛋白 × 分组 × 样本 × 丰度`，领域模型 `ProteinQuantification`）。定量**与 bundle 分离**：实验创建后
**单独、可增量**提交，落库即解锁差异分析（先算差异 → 只对差异蛋白做结构 / 假说 / deep-search）。

> **隔离开发说明**：本契约由**下游自定**，不等上游对齐。将来与上游集成时，若其定量格式不同，
> 在入口前加一层**字段映射适配器**桥接即可 —— 与本输入契约同一套打法。

### 6.1 怎么交

- **接口**：`POST /ptagent/api/experiments/{experiment_id}/quantifications`（`Content-Type: application/json`）。
- **前置**：实验须已存在（先 `POST /experiments` 建好 bundle）；未知实验 → `404`。
- **下游做什么**：逐行校验 → 落库 `ProteinQuantification` → 返回写入统计。

### 6.2 请求体

```json
{
  "quantifications": [
    {"protein_id": "prot_1", "group_id": "g_case", "sample_id": "c1", "abundance": 12500.0},
    {"protein_id": "prot_1", "group_id": "g_ctrl", "sample_id": "k1", "abundance": 8300.0}
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `protein_id` | string | ✅ | 蛋白稳定 ID；**必须存在于该实验 `proteins[]`** |
| `group_id` | string | ✅ | 分组稳定 ID；**必须存在于该实验 `groups[]`** |
| `sample_id` | string | ✅ | 样本 ID（组内区分重复，如 `c1`/`c2`/`k1`） |
| `abundance` | float | ✅ | 该样本下该蛋白的丰度 |
| `meta` | dict | 否 | 自定义（如归一化方式、批次） |

> `experiment_id` **不在行里给**（由 URL 路径决定）；若行内给了且与路径不一致 → 拒绝。

### 6.3 校验规则（强制）

1. 每行 `protein_id` ∈ 该实验蛋白；`group_id` ∈ 该实验分组。
2. 字段缺失 / 类型错（如缺 `abundance`）→ `422`。
3. **整批原子**：任一行非法 → **整批拒绝、不部分落库**，`422` 消息含每行错误位置。
4. **幂等 upsert**：同 `(protein_id, group_id, sample_id)` 重复提交按覆盖处理（更新丰度）。

### 6.4 响应 / 查询

```json
{"experiment_id": "exp_...", "received": 2, "written": 2, "proteins": 1, "groups": 2, "samples": 2}
```

往返查询：`GET /ptagent/api/experiments/{experiment_id}/quantifications` → `{count, quantifications: [...]}`。

> 肽段 `abundance`（§3.4）仅作证据留存；"肽→蛋白定量汇总"不在此入口，由本接口直接收**蛋白级**定量。

## 7. 上游**不需要**提供的

谱图原始数据、查库归属结果、蛋白推断打分、novelty 判定 —— 这些属上游内部过程，下游只要**最终已鉴定的蛋白/肽 + 分组 + 背景**。
