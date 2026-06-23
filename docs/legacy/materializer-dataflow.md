# Materializer 数据流详解（参数级）

> 把一次 `run` 的产物（`.mgf` 谱图 + `.mztab` 结果）解包进关系图谱的**逐步参数流**。
> 代码：[`materializer.py`](../src/application/graph/materializer.py) · [`loaders/casanovo.py`](../src/application/graph/loaders/casanovo.py) · [`loaders/__init__.py`](../src/application/graph/loaders/__init__.py) · 图谱写入 [`pkg/graph/cypher.py`](../src/pkg/graph/cypher.py)

贯穿全文用同一条样例：输入谱图 `sampleA.mgf`（3 张谱 index 0/1/2），结果 `res.mztab`（只有 index 0、1 被预测）。

---

## 0. 全流程一图

```
run_id="run_abc"
   │
   ▼ ① dp.get_run(run_id)                    → run 记录（in/out ids 是 JSON 串）
   ▼ ② get_loader(run.tool_name)             → casanovo.build_rows
   ▼ ③ loader(dp, run) = build_rows(...)      → list[TrunkRow]
   │     ├─ _pick 选文件（按 data_type）
   │     ├─ parse_mgf_spectra(谱图)           → list[谱]   （顺序=index）
   │     ├─ parse_casanovo_mztab_psms(结果)   → {index: psm}
   │     └─ enumerate 谱图 ⨝ psm[index] join  → TrunkRow
   ▼ ④ g.merge_trunk(rows)                    → UNWIND $rows + MERGE → Neo4j 节点/边
   ▼ ⑤ dp.update_data_object_meta(out, {...}) → 回写 SQLite：materialized:true
   │
   ▼ return {"run_id", "status":"ok", "rows": n}
```

---

## ① get_run — 取出这次运行的输入/输出文件指针

**调用**：`run = dp.get_run("run_abc")`

**得到**（原始 DB 行，注意两个 `*_object_ids` 是 **JSON 字符串**，不是 list）：

```python
{
  "run_id": "run_abc",
  "tool_name": "casanovo",
  "status": "Success",
  "input_object_ids":  '["dobj_mgf01"]',     # ← str（JSON）
  "output_object_ids": '["dobj_mztab01"]',   # ← str（JSON）
  "request_id": "prq_…",
  # …其余列省略
}
```

materializer 立刻解一次 + 做幂等闸门：

```python
out_ids = _json_ids(run, "output_object_ids")   # json.loads → ["dobj_mztab01"]
# 若 out_ids 全部已 materialized 且 force=False → return status="skipped"
```

| 出参 | 类型 | 样例 |
|---|---|---|
| `run` | `dict \| None` | 上面的记录；`None` → `status="unknown_run"` |
| `out_ids` | `list[str]` | `["dobj_mztab01"]` |

---

## ② get_loader — 按工具名选装载器

**调用**：`loader = get_loader(run["tool_name"])`  → `get_loader("casanovo")`

**逻辑**（[`loaders/__init__.py`](../src/application/graph/loaders/__init__.py)）：规范化大小写 → 查注册表 → 子串兜底。

| 入参 `tool_name` | 出参 |
|---|---|
| `"casanovo"` / `"Casanovo"` | `casanovo.build_rows` ✅ |
| `"mcp.casanovo.sequence"` | `casanovo.build_rows`（子串命中）✅ |
| `"uniprot_lookup"` / `None` | `None` → `status="no_loader"`，跳过 |

出参类型：`Callable[[DataPlaneStore, dict], list[TrunkRow]] | None`

---

## ③ build_rows — 选文件 + 解析 + 按 index join（核心）

**调用**：`rows = loader(dp, run)` → `casanovo.build_rows(dp, run)`

### 3.1 按 data_type 选文件（不盲取第 0 个）

```python
spectra_oid = _pick(dp, _ids(run,"input_object_ids"),  {"MGF","MZML"})  # → "dobj_mgf01"
result_oid  = _pick(dp, _ids(run,"output_object_ids"), {"MZTAB"})       # → "dobj_mztab01"
```

`_pick` 内部对每个 id 调 `dp.get_data_object(oid)`，看 `data_type` 是否在集合里：

```python
dp.get_data_object("dobj_mgf01") = {
  "object_id": "dobj_mgf01",
  "data_type": "MGF",
  "storage_path": "/data/…/sampleA.mgf",
  "meta_json": '{"filename": "sampleA.mgf", "source": "ingest"}',
  # …
}
```

任一为 `None`（缺谱图或缺结果）→ `build_rows` 返回 `[]` → `status="empty"`。

### 3.2 各自解析成内存结构

**谱图**：`spectra = parse_mgf_spectra(dp.storage_path(spectra_oid))` → `list[dict]`，**列表顺序即 index**：

```python
[
  {"title":"s0","precursor_mz":500.25,"precursor_charge":2,"peaks_mz":[...],"peaks_intensity":[...]},  # index 0
  {"title":"s1","precursor_mz":598.26,"precursor_charge":3,"peaks_mz":[...],"peaks_intensity":[...]},  # index 1
  {"title":"s2","precursor_mz":700.10,"precursor_charge":2,"peaks_mz":[...],"peaks_intensity":[...]},  # index 2
]
```
> ⚠️ 此解析器**不返回** `retention_time`，也不返回 `spectrum_id`。

**结果**：`psms = parse_casanovo_mztab_psms(dp.storage_path(result_oid))` → `dict[int, dict]`，key 是 mzTab `spectra_ref` 里的 `index=N`：

```python
{
  0: {"sequence":"PEPTIDE","score":0.91,"spectra_ref":"ms_run[1]:index=0","aa_scores":[0.9,0.8],"proforma":"PEPTIDE"},
  1: {"sequence":"MEEVEESPEK","score":0.98,"spectra_ref":"ms_run[1]:index=1","aa_scores":[0.99,0.97],"proforma":"MEEVEES[+79.966]PEK"},
  # index 2 没有预测 → 不在 dict 里
}
```

### 3.3 上下文

```python
sample_id, sample_name = _sample_id_from(dp, spectra_oid)   # 从谱图 meta 的 filename 推
# → ("sample:sampleA", "sampleA")
run_id = run["run_id"]                                      # "run_abc"
```

### 3.4 join：`enumerate(spectra)` ⨝ `psms[index]`

```python
for idx, spec in enumerate(spectra):     # idx = 0,1,2
    psm = psms.get(idx)
    if psm is None:                      # index 2 → 跳过
        continue
    seq = psm["sequence"]
    peptidoform = psm["proforma"] or seq # 带修饰优先，空则退裸序列
    rows.append(TrunkRow(...))
```

**join 的钥匙就是 `idx`**：mgf 第 `idx` 张谱 ↔ mzTab `index=idx` 的预测。index 2 无 PSM → 不产行。

### 3.5 一行 TrunkRow（以 index 1 为例）

| 字段 | 类型 | 值 | 来源 |
|---|---|---|---|
| `spectrum_id` | str | `"dobj_mgf01:1"` | 谱图 oid + idx（全局唯一稳定键） |
| `precursor_mz` | float | `598.26` | 谱图 `precursor_mz` |
| `charge` | int | `3` | 谱图 `precursor_charge` |
| `retention_time` | None | `None` | ⚠️ mgf 解析器不给 RT |
| `scan_index` | int | `1` | `idx` |
| `spectra_object_id` | str | `"dobj_mgf01"` | 溯源：谱图文件 |
| `psm_id` | str | `"dobj_mztab01:1"` | 结果 oid + idx（全局唯一） |
| `score` | float | `0.98` | psm `score` |
| `q_value` | None | `None` | de novo 无 FDR |
| `aa_scores` | list[float] | `[0.99, 0.97]` | psm `aa_scores` |
| `search_engine` | str | `"casanovo"` | loader 硬编码 |
| `is_decoy` | bool | `False` | de novo 无 decoy |
| `result_object_id` | str | `"dobj_mztab01"` | 溯源：结果文件 |
| `peptidoform` | str | `"MEEVEES[+79.966]PEK"` | psm `proforma`（Peptide 身份键） |
| `stripped_sequence` | str | `"MEEVEESPEK"` | psm `sequence` |
| `length` | int | `10` | `len(seq)` |
| `sample_id` | str | `"sample:sampleA"` | `_sample_id_from` |
| `sample_name` | str | `"sampleA"` | `_sample_id_from` |
| `condition` | str | `""` | 暂无来源 |
| `run_id` | str | `"run_abc"` | 溯源：本次运行 |

**出参**：`rows: list[TrunkRow]`，本例 **2 行**（idx 0、1；idx 2 跳过）。空 → `status="empty"`。

---

## ④ merge_trunk — 分批 UNWIND + MERGE 写 Neo4j

**调用**：`n = g.merge_trunk(rows)`（[`pkg/graph/store.py`](../src/pkg/graph/store.py)）

按 1000 行一批，每批以 `{"rows": [...]}` 为参数执行 [`cypher.MERGE_TRUNK`](../src/pkg/graph/cypher.py)：

```cypher
UNWIND $rows AS r
MERGE (s:Sample   {sample_id: r.sample_id})       ON CREATE SET s.name=r.sample_name, s.condition=r.condition
MERGE (sp:Spectrum {spectrum_id: r.spectrum_id})  ON CREATE SET sp.precursor_mz=r.precursor_mz, sp.charge=r.charge,
                                                                sp.retention_time=r.retention_time, sp.scan_index=r.scan_index,
                                                                sp.data_object_id=r.spectra_object_id
MERGE (s)-[:PRODUCED]->(sp)
MERGE (pep:Peptide {peptidoform: r.peptidoform})  ON CREATE SET pep.stripped_sequence=r.stripped_sequence, pep.length=r.length
MERGE (psm:PSM     {psm_id: r.psm_id})            ON CREATE SET psm.score=r.score, psm.q_value=r.q_value, psm.aa_scores=r.aa_scores,
                                                                psm.search_engine=r.search_engine, psm.is_decoy=coalesce(r.is_decoy,false),
                                                                psm.run_id=r.run_id, psm.data_object_id=r.result_object_id
MERGE (sp)-[:HAS_PSM]->(psm)
MERGE (psm)-[:IDENTIFIES]->(pep)
```

**每行 r → 图里这条链**（`MERGE` 在 `sample_id`/`spectrum_id`/`peptidoform`/`psm_id` 上幂等去重）：

```
(Sample sample:sampleA) ─PRODUCED→ (Spectrum dobj_mgf01:1) ─HAS_PSM→ (PSM dobj_mztab01:1) ─IDENTIFIES→ (Peptide MEEVEES[+79.966]PEK)
```

**出参**：`n = len(rows)`（本例 `2`）。

---

## ⑤ 盖章 — 回写 SQLite，关闭幂等闸门

**调用**：

```python
for oid in out_ids:                       # ["dobj_mztab01"]
    dp.update_data_object_meta(oid, {"materialized": True, "graph_rows": n})
```

把结果文件的 `meta_json` 合并更新为：

```python
'{"filename": "res.mztab", …, "materialized": true, "graph_rows": 2}'
```

下次再调 `materialize_run("run_abc")` → ① 的幂等闸门命中 → `status="skipped"`，不重复入图。

---

## 返回值

```python
materialize_run("run_abc") = {"run_id": "run_abc", "status": "ok", "rows": 2}
```

| status | 含义 | 触发处 |
|---|---|---|
| `ok` | 成功写入 `rows` 行 | 正常走完 |
| `skipped` | 结果文件已 materialized（`force=False`） | ① 幂等闸门 |
| `empty` | loader 无产出（非可入图形态 / 无 PSM） | ③ rows 为空 |
| `no_loader` | tool_name 无对应 loader | ② get_loader 返回 None |
| `unknown_run` | 查无此 run | ① get_run 返回 None |
| `error` | 抛异常（仅 `materialize_run_safe` 捕获） | 任意步异常 |

---

## 两条贯穿全程的设计约束

1. **幂等 / 可重跑**：节点身份键稳定（文件 oid + index、peptidoform）；`MERGE` 不产重复；**先写 Neo4j 后盖 SQLite**，中途崩了重跑也不会出现"盖了章但图没写全"的坏状态。
2. **可溯源（供合规审计）**：每个图节点都带回指针——`Spectrum.data_object_id`、`PSM.run_id` / `PSM.data_object_id`。任一鉴定可反查 `Peptide ← PSM ←(run_id)← DataObject ← 原始文件`。

## 已知留空（非 bug）

| 字段 | 现状 | 要真值需 |
|---|---|---|
| `retention_time` | `None` | 扩展 `parse_mgf_spectra` 读 `RTINSECONDS` |
| `q_value` / `is_decoy` | `None` / `False` | de novo 本就无 FDR/decoy；数据库搜索范式才有 |
| `condition` | `""` | 接入样本/分组元数据来源 |
