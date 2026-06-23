# PTAgent 闭环 · 10 步分镜（每步内部细节）

> 每一步单独放大其内部小流程，步与步之间不连线。配色：**蓝=处理、teal=进图、灰=输入/文件/在线（不进图）**。
> 整合成一张的总览见 [pipeline-steps.svg](pipeline-steps.svg)；项目规格见 [project-spec.md](project-spec.md)。
>
> 注：本文用内联 SVG，VS Code 预览 / 多数本地 Markdown 阅读器可直接渲染；GitHub 会清洗内联 SVG 可能不显示——若需在 GitHub 上看，我可以改成各自独立的 .svg 图片引用。

<style>
svg { --color-text-tertiary: #6B6B66; }
.t { font-size: 14px; font-weight: 500; }
.ts { font-size: 12px; }
svg text { font-family: "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif; fill: #141413; }
rect.c-gray, .c-gray rect { fill: #ECEAE1; stroke: #C4C2B8; }
.c-gray text { fill: #141413; }
rect.c-blue, .c-blue rect { fill: #E6F1FB; stroke: #9DC3EC; }
.c-blue text { fill: #08355F; }
rect.c-teal, .c-teal rect { fill: #E1F5EE; stroke: #7FD3B5; }
.c-teal text { fill: #06453A; }
@media (prefers-color-scheme: dark) {
  svg text { fill: #ECECE8; }
  .c-gray text, .c-blue text, .c-teal text { fill: #141413; }
}
</style>

## ① 谱图输入 · ingest

文件落盘，库里只登记指针。

<svg width="100%" viewBox="0 0 680 150" role="img" xmlns="http://www.w3.org/2000/svg">
<title>步骤1 ingest 细节</title><desc>上传mgf文件落盘，SQLite只登记DataObject与storage_path指针，峰不进库。</desc>
<defs><marker id="a1" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--color-text-tertiary)"/></marker></defs>
<g class="c-gray"><rect x="40" y="40" width="150" height="60" rx="8"/><text x="115" y="62" text-anchor="middle" dominant-baseline="central" class="t">上传 .mgf</text><text x="115" y="82" text-anchor="middle" dominant-baseline="central" class="ts">原始谱图峰（重）</text></g>
<path d="M190,70 L242,70" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a1)"/>
<g class="c-blue"><rect x="246" y="40" width="174" height="60" rx="8"/><text x="333" y="62" text-anchor="middle" dominant-baseline="central" class="t">ingest</text><text x="333" y="82" text-anchor="middle" dominant-baseline="central" class="ts">算 size · 存盘 · 建记录</text></g>
<path d="M420,70 L462,70" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a1)"/>
<g class="c-gray"><rect x="466" y="40" width="174" height="60" rx="8"/><text x="553" y="62" text-anchor="middle" dominant-baseline="central" class="t">DataObject（SQLite）</text><text x="553" y="82" text-anchor="middle" dominant-baseline="central" class="ts">MGF · storage_path</text></g>
<text x="40" y="128" class="ts">三层存储：文件存峰、SQLite 只存指针——峰不进图库。</text>
</svg>

## ② Casanovo de novo

逐张谱图推理出肽序列，此刻还没有蛋白。

<svg width="100%" viewBox="0 0 680 150" role="img" xmlns="http://www.w3.org/2000/svg">
<title>步骤2 Casanovo 细节</title><desc>每张MS2谱图经Casanovo逐谱推理出肽序列、proforma、score与每残基aa_scores，输出mzTab，此时无蛋白。</desc>
<defs><marker id="a2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--color-text-tertiary)"/></marker></defs>
<g class="c-gray"><rect x="40" y="40" width="160" height="60" rx="8"/><text x="120" y="62" text-anchor="middle" dominant-baseline="central" class="t">MS2 谱图 ×N</text><text x="120" y="82" text-anchor="middle" dominant-baseline="central" class="ts">一张张碎裂谱</text></g>
<path d="M200,70 L252,70" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a2)"/>
<g class="c-blue"><rect x="256" y="40" width="168" height="60" rx="8"/><text x="340" y="62" text-anchor="middle" dominant-baseline="central" class="t">Casanovo 逐谱推理</text><text x="340" y="82" text-anchor="middle" dominant-baseline="central" class="ts">AI de novo 测序</text></g>
<path d="M424,70 L460,70" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a2)"/>
<g class="c-gray"><rect x="464" y="40" width="176" height="60" rx="8"/><text x="552" y="62" text-anchor="middle" dominant-baseline="central" class="t">mzTab 每行</text><text x="552" y="82" text-anchor="middle" dominant-baseline="central" class="ts">seq·proforma·score·aa_scores</text></g>
<text x="40" y="128" class="ts">一张 MS2 → 一条肽（DDA）；输出只有序列和置信度，还没有蛋白。</text>
</svg>

## ③ 压扁 · loaders/casanovo

谱图文件和结果文件按扫描序号 index 配对，拼成一行行扁平记录。

<svg width="100%" viewBox="0 0 680 210" role="img" xmlns="http://www.w3.org/2000/svg">
<title>步骤3 压扁join细节</title><desc>MGF谱图与mzTab结果按index对齐join成TrunkRow扁平行，无PSM的谱跳过。</desc>
<defs><marker id="a3" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--color-text-tertiary)"/></marker></defs>
<g class="c-gray"><rect x="40" y="40" width="155" height="56" rx="8"/><text x="117" y="60" text-anchor="middle" dominant-baseline="central" class="t">MGF 谱图</text><text x="117" y="80" text-anchor="middle" dominant-baseline="central" class="ts">precursor_mz·charge·index</text></g>
<g class="c-gray"><rect x="40" y="116" width="155" height="56" rx="8"/><text x="117" y="136" text-anchor="middle" dominant-baseline="central" class="t">mzTab 结果</text><text x="117" y="156" text-anchor="middle" dominant-baseline="central" class="ts">index → {seq,score,aa}</text></g>
<path d="M195,68 L256,98" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a3)"/>
<path d="M195,144 L256,118" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a3)"/>
<g class="c-blue"><rect x="260" y="78" width="150" height="56" rx="8"/><text x="335" y="98" text-anchor="middle" dominant-baseline="central" class="t">按 index 对齐 join</text><text x="335" y="118" text-anchor="middle" dominant-baseline="central" class="ts">loaders/casanovo</text></g>
<path d="M410,106 L446,106" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a3)"/>
<g class="c-gray"><rect x="450" y="78" width="190" height="56" rx="8"/><text x="545" y="98" text-anchor="middle" dominant-baseline="central" class="t">TrunkRow（一行=一条PSM）</text><text x="545" y="118" text-anchor="middle" dominant-baseline="central" class="ts">= 谱·PSM·肽·样本 拼一行</text></g>
<text x="40" y="194" class="ts">扫描序号 index 是对齐键；spectrum_id = 文件:idx 保唯一；无 PSM 的谱跳过。</text>
</svg>

## ④ materialize 主干

扁平行按稳定键 MERGE 去重入图，建实测主干，完事给结果文件盖章。

<svg width="100%" viewBox="0 0 680 185" role="img" xmlns="http://www.w3.org/2000/svg">
<title>步骤4 materialize主干细节</title><desc>TrunkRow经MERGE_TRUNK按稳定键去重，建Sample/Spectrum/PSM/Peptide节点与PRODUCED/HAS_PSM/IDENTIFIES边，并给结果文件盖materialized章。</desc>
<defs><marker id="a4" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--color-text-tertiary)"/></marker></defs>
<g class="c-gray"><rect x="40" y="56" width="130" height="60" rx="8"/><text x="105" y="78" text-anchor="middle" dominant-baseline="central" class="t">TrunkRow ×N</text><text x="105" y="98" text-anchor="middle" dominant-baseline="central" class="ts">扁平行</text></g>
<path d="M170,86 L206,86" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a4)"/>
<g class="c-blue"><rect x="210" y="56" width="180" height="60" rx="8"/><text x="300" y="78" text-anchor="middle" dominant-baseline="central" class="t">MERGE_TRUNK 分批</text><text x="300" y="98" text-anchor="middle" dominant-baseline="central" class="ts">稳定键去重·幂等</text></g>
<path d="M390,72 L426,58" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a4)"/>
<path d="M390,100 L426,120" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a4)"/>
<g class="c-teal"><rect x="430" y="30" width="210" height="56" rx="8"/><text x="535" y="50" text-anchor="middle" dominant-baseline="central" class="t">Sample/Spectrum/PSM/Peptide</text><text x="535" y="70" text-anchor="middle" dominant-baseline="central" class="ts">PRODUCED·HAS_PSM·IDENTIFIES</text></g>
<g class="c-gray"><rect x="430" y="98" width="210" height="44" rx="8"/><text x="535" y="120" text-anchor="middle" dominant-baseline="central" class="ts">盖章 meta.materialized=true</text></g>
<text x="40" y="166" class="ts">去重键：peptidoform / spectrum_id / psm_id；先写图后盖章，重跑安全。</text>
</svg>

## ⑤ 查库归属 + 蛋白推断

上半是肽查 FASTA 定命中/novel，下半是共享肽的消歧（分组 + unique + razor）。

<svg width="100%" viewBox="0 0 680 240" role="img" xmlns="http://www.w3.org/2000/svg">
<title>步骤5 查库归属与蛋白推断细节</title><desc>上半：未查库肽经FASTA查库(I/L归一·子串)分命中→BELONGS_TO与未命中→is_novel；下半：run_inference做WCC分组、is_unique、razor处理共享肽。</desc>
<defs><marker id="a5" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--color-text-tertiary)"/></marker></defs>
<text x="40" y="26" class="ts">A. 查库 + novelty</text>
<g class="c-gray"><rect x="40" y="36" width="140" height="54" rx="8"/><text x="110" y="55" text-anchor="middle" dominant-baseline="central" class="t">未查库肽</text><text x="110" y="74" text-anchor="middle" dominant-baseline="central" class="ts">db_searched null</text></g>
<path d="M180,63 L216,63" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a5)"/>
<g class="c-blue"><rect x="220" y="36" width="180" height="54" rx="8"/><text x="310" y="55" text-anchor="middle" dominant-baseline="central" class="t">FASTA 查库</text><text x="310" y="74" text-anchor="middle" dominant-baseline="central" class="ts">I/L 归一 · 子串包含</text></g>
<path d="M400,63 L436,63" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a5)"/>
<g class="c-teal"><rect x="440" y="32" width="200" height="62" rx="8"/><text x="540" y="53" text-anchor="middle" dominant-baseline="central" class="t">命中→BELONGS_TO+Protein</text><text x="540" y="73" text-anchor="middle" dominant-baseline="central" class="ts">未命中→is_novel=true</text></g>
<text x="40" y="126" class="ts">B. 蛋白推断（共享肽消歧 · run_inference）</text>
<g class="c-blue"><rect x="40" y="138" width="150" height="68" rx="8"/><text x="115" y="162" text-anchor="middle" dominant-baseline="central" class="t">run_inference</text><text x="115" y="182" text-anchor="middle" dominant-baseline="central" class="ts">GDS 多步</text></g>
<path d="M190,172 L214,172" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a5)"/>
<g class="c-teal"><rect x="218" y="138" width="132" height="68" rx="8"/><text x="284" y="162" text-anchor="middle" dominant-baseline="central" class="t">WCC 分组</text><text x="284" y="182" text-anchor="middle" dominant-baseline="central" class="ts">→ ProteinGroup</text></g>
<g class="c-teal"><rect x="362" y="138" width="120" height="68" rx="8"/><text x="422" y="162" text-anchor="middle" dominant-baseline="central" class="t">is_unique</text><text x="422" y="182" text-anchor="middle" dominant-baseline="central" class="ts">度 = 1</text></g>
<g class="c-teal"><rect x="494" y="138" width="146" height="68" rx="8"/><text x="567" y="162" text-anchor="middle" dominant-baseline="central" class="t">razor</text><text x="567" y="182" text-anchor="middle" dominant-baseline="central" class="ts">共享肽归证据最多组</text></g>
<text x="40" y="228" class="ts">共享肽照实连所有命中蛋白；分不清的报成一组，不删事实，razor 只是主推。</text>
</svg>

## ⑥ 注释富集 · enrich_annot

按 accession 从 TSV 缓存批量取注释，贴成蛋白节点属性并记版本。

<svg width="100%" viewBox="0 0 680 160" role="img" xmlns="http://www.w3.org/2000/svg">
<title>步骤6 注释富集细节</title><desc>未富集accession去重后从TSV缓存批量fetch，组成ProtAnnotRow，经MERGE_PROT_ANNOT写成Protein的go/ec/interpro属性加provenance。</desc>
<defs><marker id="a6" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--color-text-tertiary)"/></marker></defs>
<g class="c-gray"><rect x="40" y="44" width="160" height="60" rx="8"/><text x="120" y="66" text-anchor="middle" dominant-baseline="central" class="t">未富集 accession</text><text x="120" y="86" text-anchor="middle" dominant-baseline="central" class="ts">annot_version null</text></g>
<path d="M200,74 L252,74" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a6)"/>
<g class="c-blue"><rect x="256" y="44" width="180" height="60" rx="8"/><text x="346" y="66" text-anchor="middle" dominant-baseline="central" class="t">source.fetch</text><text x="346" y="86" text-anchor="middle" dominant-baseline="central" class="ts">TSV 缓存 · 去重批量</text></g>
<path d="M436,74 L466,74" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a6)"/>
<g class="c-teal"><rect x="470" y="44" width="170" height="60" rx="8"/><text x="555" y="66" text-anchor="middle" dominant-baseline="central" class="t">Protein{go,ec,interpro}</text><text x="555" y="86" text-anchor="middle" dominant-baseline="central" class="ts">+ annot_source/version</text></g>
<text x="40" y="138" class="ts">大库不进图、TSV 当缓存；只补 annot_version 空的（幂等），源里没有的留到下次。</text>
</svg>

## ⑦ 混合检索 · retrieval

四路信号并行粗筛 → RRF 融合 → 精排 → 写相似边。

<svg width="100%" viewBox="0 0 680 268" role="img" xmlns="http://www.w3.org/2000/svg">
<title>步骤7 混合检索细节</title><desc>稠密ESM、稀疏kmer/BLAST、属性重叠、网络四路召回经RRF融合成候选topN，再rerank精排写出SIMILAR_TO相似边。</desc>
<defs><marker id="a7" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--color-text-tertiary)"/></marker></defs>
<g class="c-gray"><rect x="40" y="34" width="142" height="50" rx="8"/><text x="111" y="52" text-anchor="middle" dominant-baseline="central" class="t">稠密 ESM</text><text x="111" y="70" text-anchor="middle" dominant-baseline="central" class="ts">向量 ANN</text></g>
<g class="c-gray"><rect x="194" y="34" width="142" height="50" rx="8"/><text x="265" y="52" text-anchor="middle" dominant-baseline="central" class="t">稀疏 k-mer/BLAST</text><text x="265" y="70" text-anchor="middle" dominant-baseline="central" class="ts">局部同源</text></g>
<g class="c-gray"><rect x="348" y="34" width="142" height="50" rx="8"/><text x="419" y="52" text-anchor="middle" dominant-baseline="central" class="t">属性重叠</text><text x="419" y="70" text-anchor="middle" dominant-baseline="central" class="ts">GO/EC/域</text></g>
<g class="c-gray"><rect x="502" y="34" width="138" height="50" rx="8"/><text x="571" y="52" text-anchor="middle" dominant-baseline="central" class="t">网络（可选）</text><text x="571" y="70" text-anchor="middle" dominant-baseline="central" class="ts">STRING/通路</text></g>
<path d="M111,84 L300,126" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.3" marker-end="url(#a7)"/>
<path d="M265,84 L325,126" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.3" marker-end="url(#a7)"/>
<path d="M419,84 L355,126" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.3" marker-end="url(#a7)"/>
<path d="M571,84 L380,126" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.3" marker-end="url(#a7)"/>
<g class="c-blue"><rect x="250" y="128" width="180" height="50" rx="8"/><text x="340" y="146" text-anchor="middle" dominant-baseline="central" class="t">RRF 融合</text><text x="340" y="164" text-anchor="middle" dominant-baseline="central" class="ts">→ 候选 top-N</text></g>
<path d="M340,178 L340,196" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a7)"/>
<g class="c-blue"><rect x="250" y="198" width="180" height="46" rx="8"/><text x="340" y="221" text-anchor="middle" dominant-baseline="central" class="t">rerank 精排</text></g>
<path d="M430,221 L470,221" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a7)"/>
<g class="c-teal"><rect x="474" y="196" width="166" height="50" rx="8"/><text x="557" y="214" text-anchor="middle" dominant-baseline="central" class="t">SIMILAR_TO</text><text x="557" y="232" text-anchor="middle" dominant-baseline="central" class="ts">{score, method}</text></g>
</svg>

## ⑧ 假说 · hypothesize

顺相似边取邻居母蛋白属性（按 accession 保出处），取共识算置信度。

<svg width="100%" viewBox="0 0 680 210" role="img" xmlns="http://www.w3.org/2000/svg">
<title>步骤8 假说细节</title><desc>query肽顺SIMILAR_TO取带分邻居，并其母蛋白属性按accession分组，取共识算置信度=相似度×共识度，产出不入图的HypothesisRow。</desc>
<defs><marker id="a8" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--color-text-tertiary)"/></marker></defs>
<g class="c-gray"><rect x="40" y="40" width="110" height="54" rx="8"/><text x="95" y="67" text-anchor="middle" dominant-baseline="central" class="t">query 肽</text></g>
<path d="M150,67 L184,67" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a8)"/>
<g class="c-blue"><rect x="188" y="40" width="148" height="54" rx="8"/><text x="262" y="60" text-anchor="middle" dominant-baseline="central" class="t">SIMILAR_TO 邻居</text><text x="262" y="80" text-anchor="middle" dominant-baseline="central" class="ts">带相似度 score</text></g>
<path d="M336,67 L370,67" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a8)"/>
<g class="c-blue"><rect x="374" y="40" width="150" height="54" rx="8"/><text x="449" y="60" text-anchor="middle" dominant-baseline="central" class="t">邻居母蛋白属性</text><text x="449" y="80" text-anchor="middle" dominant-baseline="central" class="ts">按 accession 保出处</text></g>
<path d="M524,67 L558,67" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a8)"/>
<g class="c-blue"><rect x="562" y="40" width="78" height="54" rx="8"/><text x="601" y="67" text-anchor="middle" dominant-baseline="central" class="t">取共识</text></g>
<path d="M601,94 L601,118 L340,118 L340,134" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a8)"/>
<g class="c-gray"><rect x="40" y="136" width="600" height="52" rx="8"/><text x="340" y="155" text-anchor="middle" dominant-baseline="central" class="t">HypothesisRow（不入图）</text><text x="340" y="174" text-anchor="middle" dominant-baseline="central" class="ts">predicted · support{neighbor, via} · confidence = 相似度 × 共识度</text></g>
</svg>

## ⑨ deep-search（在线）

拿假说去网上"搜→读→抽→再搜"循环找证据，全程不落库。

<svg width="100%" viewBox="0 0 680 200" role="img" xmlns="http://www.w3.org/2000/svg">
<title>步骤9 deep-search细节</title><desc>假说建检索式后在线检索论文疾病，读取抽取，可循环再搜，得到支持或否定证据，不入图不建库。</desc>
<defs><marker id="a9" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--color-text-tertiary)"/></marker></defs>
<g class="c-gray"><rect x="40" y="64" width="96" height="50" rx="8"/><text x="88" y="89" text-anchor="middle" dominant-baseline="central" class="t">假说</text></g>
<path d="M136,89 L168,89" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a9)"/>
<g class="c-blue"><rect x="172" y="64" width="120" height="50" rx="8"/><text x="232" y="89" text-anchor="middle" dominant-baseline="central" class="t">建检索式</text></g>
<path d="M292,89 L324,89" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a9)"/>
<g class="c-blue"><rect x="328" y="64" width="140" height="50" rx="8"/><text x="398" y="84" text-anchor="middle" dominant-baseline="central" class="t">在线检索</text><text x="398" y="102" text-anchor="middle" dominant-baseline="central" class="ts">论文/疾病/实验</text></g>
<path d="M468,89 L500,89" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a9)"/>
<g class="c-blue"><rect x="504" y="64" width="120" height="50" rx="8"/><text x="564" y="89" text-anchor="middle" dominant-baseline="central" class="t">读取 · 抽取</text></g>
<path d="M564,64 C564,36 398,36 398,62" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.3" stroke-dasharray="4 3" marker-end="url(#a9)"/>
<text x="481" y="34" text-anchor="middle" class="ts">再搜（循环）</text>
<path d="M564,114 L564,142 L340,142 L340,150" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a9)"/>
<g class="c-gray"><rect x="190" y="152" width="300" height="40" rx="8"/><text x="340" y="172" text-anchor="middle" dominant-baseline="central" class="ts">证据（支持/否定）· 不入图、不建库、用完即走</text></g>
</svg>

## ⑩ 报告生成

把假说、证据、图谱统计汇总成 Markdown 报告交付，闭环闭合。

<svg width="100%" viewBox="0 0 680 210" role="img" xmlns="http://www.w3.org/2000/svg">
<title>步骤10 报告细节</title><desc>假说集、证据、图谱统计三路汇总组织成Markdown报告交付，谱图进报告出闭环闭合。</desc>
<defs><marker id="a10" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--color-text-tertiary)"/></marker></defs>
<g class="c-gray"><rect x="40" y="36" width="156" height="44" rx="8"/><text x="118" y="58" text-anchor="middle" dominant-baseline="central" class="ts">假说集</text></g>
<g class="c-gray"><rect x="40" y="90" width="156" height="44" rx="8"/><text x="118" y="112" text-anchor="middle" dominant-baseline="central" class="ts">证据（在线）</text></g>
<g class="c-gray"><rect x="40" y="144" width="156" height="44" rx="8"/><text x="118" y="166" text-anchor="middle" dominant-baseline="central" class="ts">图谱统计 support/group</text></g>
<path d="M196,58 L252,98" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.3" marker-end="url(#a10)"/>
<path d="M196,112 L252,112" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.3" marker-end="url(#a10)"/>
<path d="M196,166 L252,126" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.3" marker-end="url(#a10)"/>
<g class="c-blue"><rect x="256" y="84" width="176" height="56" rx="8"/><text x="344" y="104" text-anchor="middle" dominant-baseline="central" class="t">汇总 → Markdown</text><text x="344" y="124" text-anchor="middle" dominant-baseline="central" class="ts">发现 / 证据 / 方法 段落</text></g>
<path d="M432,112 L466,112" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.4" marker-end="url(#a10)"/>
<g class="c-gray"><rect x="470" y="84" width="170" height="56" rx="8"/><text x="555" y="104" text-anchor="middle" dominant-baseline="central" class="t">交付报告</text><text x="555" y="124" text-anchor="middle" dominant-baseline="central" class="ts">谱图进、报告出</text></g>
</svg>
