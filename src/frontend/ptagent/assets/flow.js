/* global vis */

/** @type {{ builtinFields: any[], conventionFields: any[], allKeys: string[] }} */
let FIELD_CATALOG = { builtinFields: [], conventionFields: [], allKeys: [] };

/** 工业图入口键（来自起点对话框，仅 CONVENTIONS） */
let currentInputKeys = [];

const COLORS = {
  start: { background: "#2d6a4f", border: "#1b4332", font: { color: "#fff" } },
  end: { background: "#9d0208", border: "#6a040f", font: { color: "#fff" } },
  agent: { background: "#4361ee", border: "#3a0ca3", font: { color: "#fff" } },
  tool: { background: "#f77f00", border: "#d62828", font: { color: "#fff" } },
  legacy: { background: "#6c757d", border: "#495057", font: { color: "#fff" } },
};

let network = null;
let nodes = null;
let edges = null;
/** @type {Record<string, any>} */
let nodeMeta = {};
/** @type {string|null} */
let selectedId = null;
/** @type {string|null} */
let selectedEdgeId = null;
/** @type {any[]} */
let mcpTools = [];

/** @type {number} */
let nodeIdCounter = 0;

const dlgStart = () => document.getElementById("dlgStart");
const dlgNode = () => document.getElementById("dlgNode");

function uid(prefix) {
  return (prefix || "n") + Math.random().toString(36).slice(2, 9);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s) {
  return String(s).replace(/"/g, "&quot;");
}

function dirIn(d) {
  return d === "request" || d === "both";
}
function dirOut(d) {
  return d === "response" || d === "both";
}

function addCheckboxRow(container, name, key, title, checked) {
  const lab = document.createElement("label");
  lab.className = "chk";
  lab.title = title || key;
  const inp = document.createElement("input");
  inp.type = "checkbox";
  inp.name = name;
  inp.value = key;
  inp.checked = !!checked;
  inp.addEventListener("change", updateValidation);
  lab.appendChild(inp);
  lab.appendChild(document.createTextNode(` ${key}`));
  container.appendChild(lab);
}

/** 保存 Team 时写入 graph.outputKeys：由约定自动生成；运行结束时出口仍在 state.data 根级 */
function inferDefaultOutputKeys() {
  const keys = new Set(["working_note"]);
  for (const row of FIELD_CATALOG.builtinFields || []) {
    if (dirOut(row.direction)) keys.add(row.key);
  }
  for (const row of FIELD_CATALOG.conventionFields || []) {
    if (dirOut(row.direction)) keys.add(row.key);
  }
  return [...keys].sort();
}

function renderStartDialogFields() {
  const box = document.getElementById("dlgStartConvKeys");
  box.innerHTML = "";
  const selected = new Set(currentInputKeys);
  const rows = FIELD_CATALOG.conventionFields || [];
  let any = false;
  for (const row of rows) {
    if (!dirIn(row.direction)) continue;
    any = true;
    const k = row.key;
    const note = row.note || "";
    const wrap = document.createElement("div");
    wrap.className = "flow-conv-field";
    wrap.innerHTML = `<label class="chk flow-conv-label"><input type="checkbox" name="startConv" value="${escapeAttr(
      k
    )}" ${selected.has(k) ? "checked" : ""}/> <strong>${escapeHtml(k)}</strong></label>
      <div class="muted small flow-conv-note">${escapeHtml(note)}</div>`;
    box.appendChild(wrap);
  }
  if (!any) {
    box.innerHTML = '<p class="muted small">当前约定中无可作为请求传入的字段，请检查 config.mcp_conventions。</p>';
  }
}

function getCheckedKeys(name) {
  return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map((x) => x.value);
}

function syncGraphKeysFromTeam(g) {
  const ik = g.inputKeys || [];
  currentInputKeys = [...ik];
}

function nodeLabel(id) {
  const m = nodeMeta[id] || {};
  const k = m.kind || "agent";
  if (k === "start") return `${id}\n[start]`;
  if (k === "end") return `${id}\n[end]`;
  if (k === "tool") return `${id}\n🔧 ${m.toolName || "?"}`;
  if (k === "agent") return `${id}\n🤖 ${m.agentKey || "?"}`;
  return `${id}\n${m.agentKey || "?"}`;
}

function syncNodeVisual(id) {
  const m = nodeMeta[id] || {};
  const k = m.kind || "legacy";
  const col = COLORS[k] || COLORS.legacy;
  nodes.update({ id, label: nodeLabel(id), color: col });
}

function nextPosition() {
  const n = nodes.getIds().length;
  return { x: 120 + (n % 4) * 200, y: 100 + Math.floor(n / 4) * 130 };
}

function reseedIdCounter() {
  let m = 0;
  for (const id of nodes.getIds()) {
    const s = String(id);
    if (/^\d+$/.test(s)) m = Math.max(m, parseInt(s, 10));
  }
  nodeIdCounter = m;
}

function allocateNodeId() {
  nodeIdCounter += 1;
  return String(nodeIdCounter);
}

async function loadFieldCatalog() {
  const r = await fetch("/ptagent-admin/api/workflow-data-keys");
  FIELD_CATALOG = await r.json();
  if (!FIELD_CATALOG.allKeys || !FIELD_CATALOG.allKeys.length) {
    FIELD_CATALOG.allKeys = ["task", "working_note"];
  }
}

async function loadAgentsSelect() {
  const r = await fetch("/ptagent-admin/api/agents");
  const d = await r.json();
  const sel = document.getElementById("dlgPickAgent");
  sel.innerHTML = "";
  for (const a of d.agents || []) {
    const o = document.createElement("option");
    o.value = a.key;
    o.textContent = `${a.key} (${a.name || ""})`;
    sel.appendChild(o);
  }
}

async function loadMcpToolsSelect() {
  const r = await fetch("/ptagent-admin/api/mcp-resources");
  const d = await r.json();
  mcpTools = d.tools || [];
  const sel = document.getElementById("dlgPickTool");
  sel.innerHTML = "";
  for (const t of mcpTools) {
    const o = document.createElement("option");
    o.value = t.name;
    o.textContent = t.name;
    sel.appendChild(o);
  }
}

/** 工业图入口 = 唯一 kind=start 的节点；旧版链无起点时用第一个节点 id */
function getGraphEntry() {
  const startId = Object.keys(nodeMeta).find((id) => {
    const mm = nodeMeta[id];
    return mm && mm.kind === "start";
  });
  if (startId) return startId;
  const ids = nodes.getIds();
  return ids.length ? ids[0] : "";
}

function rebuildEntrySelect() {
  updateValidation();
}

function countKind(kind) {
  return Object.values(nodeMeta).filter((m) => m.kind === kind).length;
}

function clientForkHints() {
  const byFrom = {};
  for (const e of edges.get()) {
    const f = String(e.from);
    byFrom[f] = (byFrom[f] || 0) + 1;
  }
  const msgs = [];
  for (const [f, c] of Object.entries(byFrom)) {
    if (c > 1) msgs.push(`节点 ${f} 有 ${c} 条出边（并行）`);
  }
  return msgs;
}

function updateValidation() {
  const el = document.getElementById("validationBanner");
  const msgs = [];
  const nodeList = nodes.getIds().map((id) => graphNodePayload(id));
  const industrial = nodeList.some((n) => n.kind && n.kind !== "agent");
  if (industrial) {
    if (countKind("start") !== 1) msgs.push("工业图需要恰好 1 个起点");
    if (countKind("end") !== 1) msgs.push("工业图需要恰好 1 个结束");
    for (const id of nodes.getIds()) {
      const m = nodeMeta[id];
      if (!m) continue;
      if (m.kind === "tool") {
        const t = mcpTools.find((x) => x.name === m.toolName);
        const sch = t && t.inputSchema;
        const { miss } = toolSchemaCheck(sch, m.argKeys || []);
        if (miss.length) msgs.push(`节点 ${id}：工具入参缺 ${miss.join(", ")}`);
      }
      if (m.kind === "agent" && !(m.agentKey || "").trim()) msgs.push(`节点 ${id}：未设置 Agent`);
    }
    msgs.push(...clientForkHints());
  } else if (nodes.getIds().length) {
    if (nodeList.some((n) => !n.agentKey)) msgs.push("旧版链：每节点需 agentKey");
  }
  el.textContent = msgs.length ? "⚠ " + msgs.join(" · ") : "✓ 工作流设计校验通过（保存时仍以后端为准）";
  el.className = msgs.length ? "validation-banner bad" : "validation-banner ok";
}

function ensureIndustrialConstraints(kind) {
  if (kind === "start" && countKind("start") >= 1) {
    alert("已存在起点节点");
    return false;
  }
  if (kind === "end" && countKind("end") >= 1) {
    alert("已存在结束节点");
    return false;
  }
  return true;
}

function toolSchemaCheck(inputSchema, argKeys) {
  const schema = inputSchema && typeof inputSchema === "object" ? inputSchema : null;
  const props = schema && schema.properties && typeof schema.properties === "object" ? schema.properties : {};
  const keys = Object.keys(props);
  const required = Array.isArray(schema && schema.required) ? schema.required.filter((k) => keys.includes(k)) : [];
  const miss = required.filter((k) => !argKeys.includes(k));
  return { keys, required, miss };
}

/**
 * 推断工具返回 dict 并平铺时可能出现的顶层键：优先 outputSchema.properties；
 * 若无则用 inputSchema.properties 作启发式（部分工具未声明 outputSchema）。
 */
function toolFlatKeysHint(toolName) {
  const t = mcpTools.find((x) => x.name === toolName);
  if (!t) return { keys: null, heuristic: false };
  const os = t.outputSchema;
  if (os && typeof os === "object" && os.properties && typeof os.properties === "object") {
    return { keys: Object.keys(os.properties), heuristic: false };
  }
  const ins = t.inputSchema;
  if (ins && typeof ins === "object" && ins.properties && typeof ins.properties === "object") {
    return { keys: Object.keys(ins.properties), heuristic: true };
  }
  return { keys: null, heuristic: false };
}

function buildSuccFromEdges(edgeList) {
  const succ = {};
  for (const e of edgeList) {
    const f = String(e.from);
    const t = String(e.to);
    if (!succ[f]) succ[f] = [];
    succ[f].push(t);
  }
  return succ;
}

function buildPredFromEdges(edgeList) {
  const pred = {};
  for (const e of edgeList) {
    const f = String(e.from);
    const t = String(e.to);
    if (!pred[t]) pred[t] = [];
    pred[t].push(f);
  }
  return pred;
}

/** 自入口 BFS 分层（用于排版） */
function bfsLayersFromEntry(entry, allIds, edgeList) {
  const succ = buildSuccFromEdges(edgeList);
  const layer = {};
  const q = [entry];
  const seen = new Set([entry]);
  layer[entry] = 0;
  while (q.length) {
    const u = q.shift();
    for (const v of succ[u] || []) {
      if (!seen.has(v)) {
        seen.add(v);
        layer[v] = layer[u] + 1;
        q.push(v);
      }
    }
  }
  for (const id of allIds) {
    if (layer[id] === undefined) layer[id] = 0;
  }
  return { layer, succ };
}

/** 拓扑序（从入口），保证计算 after 时前驱已处理 */
function topologicalOrder(entry, allIds, edgeList) {
  const succ = buildSuccFromEdges(edgeList);
  const indeg = {};
  for (const id of allIds) indeg[id] = 0;
  for (const e of edgeList) indeg[String(e.to)]++;
  indeg[entry] = 0;
  const order = [];
  const q = [entry];
  const seen = new Set();
  while (q.length) {
    const u = q.shift();
    if (seen.has(u)) continue;
    seen.add(u);
    order.push(u);
    for (const v of succ[u] || []) {
      indeg[v]--;
      if (indeg[v] === 0) q.push(v);
    }
  }
  for (const id of allIds) {
    if (!seen.has(id)) order.push(id);
  }
  return order;
}

/**
 * 静态推断各节点执行前后 state.data 中可能出现的键（启发式）。
 * @returns {Record<string, { before: Set<string>, after: Set<string>, newKeys: string[], overwriteKeys: string[] }>}
 */
function computeStateDataFlow() {
  const entry = getGraphEntry();
  const allIds = nodes.getIds();
  const edgeList = edges.get();
  const pred = buildPredFromEdges(edgeList);
  const k0 = new Set(["task", ...currentInputKeys]);

  const sortedIds = topologicalOrder(entry, allIds, edgeList);
  const afterMap = {};

  const out = {};
  for (const n of sortedIds) {
    const m = nodeMeta[n] || {};
    const kind = m.kind || "agent";

    let before = new Set();
    if (n === entry) {
      before = new Set(k0);
    } else {
      const ps = pred[n] || [];
      if (ps.length === 0) before = new Set(k0);
      else {
        for (const p of ps) {
          const as = afterMap[p];
          if (as) for (const k of as) before.add(k);
        }
      }
    }

    const after = new Set(before);
    const newKeys = [];
    const overwriteKeys = [];

    if (kind === "start") {
      /* 仅透传 */
    } else if (kind === "tool") {
      const hint = toolFlatKeysHint(m.toolName);
      const predOut = hint.keys;
      const toolFlatKeys = [];
      const toolFlatHeuristic = hint.heuristic;
      if (predOut && predOut.length) {
        for (const key of predOut) {
          toolFlatKeys.push(key);
          if (before.has(key)) overwriteKeys.push(key);
          else newKeys.push(key);
          after.add(key);
        }
      } else {
        newKeys.push("(无 schema：dict 时平铺键依运行期返回值；非 dict 时写入单键)");
      }
      if (before.has("working_note")) overwriteKeys.push("working_note");
      else newKeys.push("working_note");
      after.add("working_note");
      if (before.has("last_tool")) overwriteKeys.push("last_tool");
      else newKeys.push("last_tool");
      after.add("last_tool");
      afterMap[n] = after;
      const uniq = (arr) => [...new Set(arr)];
      out[n] = {
        before,
        after,
        newKeys: uniq(newKeys),
        overwriteKeys: uniq(overwriteKeys),
        toolFlatKeys: toolFlatKeys.length ? toolFlatKeys : null,
        toolFlatHeuristic,
      };
      continue;
    } else if (kind === "agent") {
      if (before.has("working_note")) overwriteKeys.push("working_note");
      else newKeys.push("working_note");
      after.add("working_note");
    } else if (kind === "end") {
      /* 结束节点不改写 data，仅日志 */
    }

    afterMap[n] = after;
    const uniq = (arr) => [...new Set(arr)];
    out[n] = {
      before,
      after,
      newKeys: uniq(newKeys),
      overwriteKeys: uniq(overwriteKeys),
    };
  }
  return out;
}

function formatKeySet(s) {
  if (!s || !s.size) return "（空）";
  return [...s].sort().join(", ");
}

function autoLayoutDAG() {
  const entry = getGraphEntry();
  if (!entry || !nodes.get(entry)) {
    alert("请先加载图；工业编排需含唯一起点节点");
    return;
  }
  const allIds = nodes.getIds();
  const edgeList = edges.get();
  const { layer } = bfsLayersFromEntry(entry, allIds, edgeList);
  const byLevel = {};
  for (const id of allIds) {
    const L = layer[id] ?? 0;
    if (!byLevel[L]) byLevel[L] = [];
    byLevel[L].push(id);
  }
  Object.keys(byLevel)
    .map((x) => parseInt(x, 10))
    .sort((a, b) => a - b)
    .forEach((L) => {
      const row = byLevel[L];
      row.forEach((id, j) => {
        nodes.update({
          id,
          x: 100 + L * 260,
          y: 100 + j * 125,
          fixed: { x: true, y: true },
        });
      });
    });
  if (network) network.fit({ animation: { duration: 280, easingFunction: "easeInOutQuad" } });
}

function addNodeCore(id, meta, pos) {
  nodeMeta[id] = meta;
  const k = meta.kind || "legacy";
  const col = COLORS[k] || COLORS.legacy;
  nodes.add({ id, label: nodeLabel(id), color: col, ...pos });
  syncNodeVisual(id);
  rebuildEntrySelect();
  refreshEdgeList();
}

function bindCanvasWheel() {
  const el = document.getElementById("flowNet");
  el.addEventListener(
    "wheel",
    (e) => {
      if (!e.ctrlKey && !e.metaKey) {
        e.preventDefault();
      }
    },
    { passive: false }
  );
}

function initNet() {
  const el = document.getElementById("flowNet");
  nodes = new vis.DataSet([]);
  edges = new vis.DataSet([]);
  nodeMeta = {};
  const data = { nodes, edges };
  const options = {
    physics: false,
    interaction: {
      hover: true,
      multiselect: true,
      dragNodes: true,
      navigationButtons: false,
      zoomSpeed: 0.35,
      zoomView: true,
      dragView: true,
    },
    manipulation: {
      enabled: true,
      initiallyActive: false,
    },
    edges: { arrows: "to", smooth: { type: "cubicBezier" } },
    nodes: { shape: "box", margin: 10, font: { multi: true, size: 13 } },
  };
  network = new vis.Network(el, data, options);
  bindCanvasWheel();

  network.on("select", (p) => {
    if (p.nodes.length === 1) {
      selectedId = p.nodes[0];
      selectedEdgeId = null;
      document.getElementById("inspEdge").style.display = "none";
      renderNodeInspector(selectedId);
      return;
    }
    if (p.edges.length === 1 && p.nodes.length === 0) {
      selectedId = null;
      selectedEdgeId = p.edges[0];
      document.getElementById("inspBody").style.display = "none";
      document.getElementById("inspHint").style.display = "none";
      renderEdgeInspector(selectedEdgeId);
      return;
    }
    selectedId = null;
    selectedEdgeId = null;
    document.getElementById("inspBody").style.display = "none";
    document.getElementById("inspEdge").style.display = "none";
    document.getElementById("inspHint").style.display = "block";
    updateValidation();
  });

  nodes.on("*", () => {
    updateValidation();
    refreshEdgeList();
  });
  edges.on("*", () => {
    updateValidation();
    refreshEdgeList();
  });
}

function refreshEdgeList() {
  const wrap = document.getElementById("edgeListWrap");
  const list = edges.get();
  if (!list.length) {
    wrap.innerHTML = '<p class="muted small">暂无连线。</p>';
    return;
  }
  const rows = list
    .map((e) => {
      const eid = escapeAttr(String(e.id));
      return `<tr>
        <td><code>${escapeHtml(String(e.from))}</code></td>
        <td class="edge-arr">→</td>
        <td><code>${escapeHtml(String(e.to))}</code></td>
        <td><button type="button" class="btn btn-sm edge-del" data-eid="${eid}">删除</button></td>
      </tr>`;
    })
    .join("");
  wrap.innerHTML = `<table class="edge-mini-tbl"><thead><tr><th>从</th><th></th><th>到</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
  wrap.querySelectorAll(".edge-del").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-eid");
      if (id) edges.remove(id);
    });
  });
}

function renderEdgeInspector(edgeId) {
  const e = edges.get(edgeId);
  if (!e) return;
  const el = document.getElementById("inspEdge");
  el.style.display = "block";
  el.innerHTML = `<p><strong>边</strong></p>
    <p><code>${escapeHtml(String(e.from))}</code> → <code>${escapeHtml(String(e.to))}</code></p>
    <p><button type="button" class="btn" id="btnDelThisEdge">删除此边</button></p>`;
  document.getElementById("btnDelThisEdge").addEventListener("click", () => {
    edges.remove(edgeId);
    el.style.display = "none";
    document.getElementById("inspHint").style.display = "block";
  });
}

function renameNode(oldId, newId) {
  newId = newId.trim();
  if (!newId || newId === oldId) return;
  if (nodes.get(newId)) {
    alert("该 ID 已存在");
    return;
  }
  const nd = nodes.get(oldId);
  const meta = nodeMeta[oldId];
  if (!nd || !meta) return;
  delete nodeMeta[oldId];
  nodeMeta[newId] = meta;
  nodes.remove(oldId);
  nodes.add({
    ...nd,
    id: newId,
    label: nodeLabel(newId),
    color: nd.color || COLORS[meta.kind] || COLORS.legacy,
  });
  for (const edge of edges.get()) {
    let from = edge.from;
    let to = edge.to;
    let ch = false;
    if (from === oldId) {
      from = newId;
      ch = true;
    }
    if (to === oldId) {
      to = newId;
      ch = true;
    }
    if (ch) edges.update({ id: edge.id, from, to });
  }
  network.selectNodes([newId]);
  rebuildEntrySelect();
  renderNodeInspector(newId);
  reseedIdCounter();
  updateValidation();
}

function renderNodeInspector(id) {
  document.getElementById("inspHint").style.display = "none";
  const body = document.getElementById("inspBody");
  body.style.display = "block";
  const m = nodeMeta[id] || {};
  const k = m.kind || "agent";
  let html = `<p class="flow-insp-head"><strong>${escapeHtml(k)}</strong> <code>${escapeHtml(id)}</code></p>`;
  html += `<p class="flow-rename"><label>重命名 ID<br/><span class="flow-id-row"><input type="text" id="inspRenameId" value="${escapeAttr(id)}" /><button type="button" class="btn btn-sm" id="btnInspRename">应用</button></span></label></p>`;

  let dfHtml = "";
  try {
    const flow = computeStateDataFlow();
    const d = flow[id];
    if (d) {
      const mk = m.kind || "agent";
      if (mk === "tool" && d && Object.prototype.hasOwnProperty.call(d, "toolFlatKeys")) {
        const flatNote =
          d.toolFlatKeys && d.toolFlatKeys.length
            ? d.toolFlatKeys.join(", ") + (d.toolFlatHeuristic ? "（无 outputSchema，按入参键推断）" : "")
            : "（无 schema，运行期 dict 平铺键未知）";
        dfHtml = `<div class="flow-df-block">
        <h4 class="flow-df-h">进入本节点前（预计已有键）</h4>
        <pre class="flow-df-pre">${escapeHtml(formatKeySet(d.before))}</pre>
        <h4 class="flow-df-h">工具 dict 平铺（预计顶层键）</h4>
        <pre class="flow-df-pre">${escapeHtml(flatNote)}</pre>
        <h4 class="flow-df-h">系统写入（每次执行）</h4>
        <pre class="flow-df-pre">working_note, last_tool</pre>
        <h4 class="flow-df-h">可能与已有键重叠（后写覆盖）</h4>
        <pre class="flow-df-pre">${escapeHtml(d.overwriteKeys.length ? d.overwriteKeys.join(", ") : "—")}</pre>
      </div>`;
      } else {
        dfHtml = `<div class="flow-df-block">
        <h4 class="flow-df-h">进入本节点前（预计已有键）</h4>
        <pre class="flow-df-pre">${escapeHtml(formatKeySet(d.before))}</pre>
        <h4 class="flow-df-h">经过本节点后（预计新增键）</h4>
        <pre class="flow-df-pre">${escapeHtml(d.newKeys.length ? d.newKeys.join(", ") : mk === "end" ? "（结束节点不改写 data）" : "（无或依赖运行期返回值）")}</pre>
        <h4 class="flow-df-h">可能与已有键重叠（后写覆盖）</h4>
        <pre class="flow-df-pre">${escapeHtml(d.overwriteKeys.length ? d.overwriteKeys.join(", ") : "—")}</pre>
      </div>`;
      }
    }
  } catch {
    dfHtml = '<p class="muted small">数据流推断失败（图可能不连通）。</p>';
  }
  html += dfHtml;

  if (k === "agent") {
    html += `<p><label>agentKey<br/><input type="text" data-k="agentKey" value="${escapeAttr(m.agentKey || "")}" class="flow-inp-wide"/></label></p>`;
  } else if (k === "tool") {
    html += `<p class="muted small">工具配置请在添加时选定；要更换请删除节点后重新添加。</p>`;
    html += `<p><strong>toolName</strong> <code>${escapeHtml(m.toolName || "")}</code></p>`;
    html += `<p><strong>argKeys</strong> <code>${escapeHtml((m.argKeys || []).join(", "))}</code></p>`;
    html += `<p class="muted small">返回值为 <strong>JSON 对象</strong> 时，顶层键会平铺进 <code>state.data</code>。</p>`;
    const t = mcpTools.find((x) => x.name === m.toolName);
    const chk = toolSchemaCheck(t && t.inputSchema, m.argKeys || []);
    if (chk.miss.length) {
      html += `<p class="pill bad">入参校验：缺 ${escapeHtml(chk.miss.join(", "))}</p>`;
    } else {
      html += `<p class="pill ok">入参满足 schema 必选</p>`;
    }
  } else if (k === "end") {
    html += `<p class="muted small">保存 Team 时会自动生成 <code>graph.outputKeys</code>（约定出口字段 + <code>working_note</code>）；运行结束时出口数据在 <code>state.data</code> 根级。</p>`;
  } else if (k === "start") {
    html += `<p class="muted small">入口键（CONVENTIONS）：<code>${escapeHtml(currentInputKeys.join(", ") || "（空）")}</code></p>`;
  }
  body.innerHTML = html;
  document.getElementById("btnInspRename").addEventListener("click", () => {
    const inp = document.getElementById("inspRenameId");
    renameNode(id, inp.value);
  });
  body.querySelectorAll("input[data-k]").forEach((inp) => {
    inp.addEventListener("change", () => {
      const key = inp.getAttribute("data-k");
      const mm = nodeMeta[id];
      if (key === "agentKey") mm.agentKey = inp.value.trim();
      syncNodeVisual(id);
      rebuildEntrySelect();
      renderNodeInspector(id);
    });
  });
}

function graphNodePayload(id) {
  const m = nodeMeta[id];
  if (!m) return { id, kind: "agent", agentKey: "" };
  const k = m.kind;
  if (k === "start") return { id, kind: "start" };
  if (k === "end") {
    return { id, kind: "end" };
  }
  if (k === "tool") {
    const payload = {
      id,
      kind: "tool",
      toolName: m.toolName,
      argKeys: m.argKeys || ["task"],
      flattenOutput: m.flattenOutput !== false,
    };
    if (m.flattenOutput === false) {
      payload.outputKey = m.outputKey || `${id}_out`;
    }
    return payload;
  }
  return { id, kind: "agent", agentKey: m.agentKey || "" };
}

function updateDlgCtxSummary() {
  const el = document.getElementById("dlgCtxSummary");
  const keys = currentInputKeys.length ? currentInputKeys.join(", ") : "（未选 CONVENTIONS 入口键）";
  el.innerHTML = `<strong>当前入口键</strong>（起点已选）：<code>${escapeHtml(keys)}</code>。<br/>
    运行器始终注入 <code>task</code>。Agent/工具从 <code>state.data</code> 读取上述键及 task。`;
}

function syncDlgNodeKindUi() {
  const kind = [...document.querySelectorAll('input[name="dlgNodeKind"]')].find((r) => r.checked)?.value || "agent";
  document.getElementById("dlgNodeAgentBlock").style.display = kind === "agent" ? "block" : "none";
  document.getElementById("dlgNodeToolBlock").style.display = kind === "tool" ? "block" : "none";
  validateDlgNodePreview();
}

function renderToolArgCheckboxes(toolName) {
  const box = document.getElementById("dlgToolArgKeys");
  box.innerHTML = "";
  const t = mcpTools.find((x) => x.name === toolName);
  const sch = t && t.inputSchema;
  const { keys, required } = toolSchemaCheck(sch, []);
  if (!keys.length) {
    const lab = document.createElement("div");
    lab.className = "muted small";
    lab.textContent = "该工具未提供 inputSchema；将默认使用 task。添加后不可在此改 argKeys，请删节点重加。";
    box.appendChild(lab);
    return;
  }
  for (const k of keys) {
    addCheckboxRow(box, "dlgArg", k, "", required.includes(k));
  }
}

function validateDlgNodePreview() {
  const el = document.getElementById("dlgNodeValidation");
  const kind = [...document.querySelectorAll('input[name="dlgNodeKind"]')].find((r) => r.checked)?.value || "agent";
  if (kind === "agent") {
    const v = document.getElementById("dlgPickAgent").value;
    el.textContent = v ? "✓ 将添加 Agent 节点，读写 state.data（含 working_note）" : "请选择 Agent";
    el.className = "dlg-validation " + (v ? "ok" : "bad");
    return;
  }
  const tn = document.getElementById("dlgPickTool").value;
  if (!tn) {
    el.textContent = "请选择工具";
    el.className = "dlg-validation bad";
    return;
  }
  const argKeys = getCheckedKeys("dlgArg");
  const t = mcpTools.find((x) => x.name === tn);
  const { miss } = toolSchemaCheck(t && t.inputSchema, argKeys);
  if (miss.length) {
    el.textContent = "缺少必选入参: " + miss.join(", ");
    el.className = "dlg-validation bad";
  } else {
    const th = toolFlatKeysHint(tn);
    const hint =
      th.keys && th.keys.length
        ? `dict 平铺键: ${th.keys.join(", ")}${th.heuristic ? "（按入参推断）" : ""}`
        : "dict 平铺键见 MCP outputSchema（若未声明则运行期决定）";
    el.textContent = `✓ ${hint}；并更新 working_note / last_tool`;
    el.className = "dlg-validation ok";
  }
}

document.querySelectorAll('input[name="dlgNodeKind"]').forEach((r) => {
  r.addEventListener("change", syncDlgNodeKindUi);
});

document.getElementById("btnOpenStart").addEventListener("click", () => {
  if (!ensureIndustrialConstraints("start")) return;
  renderStartDialogFields();
  dlgStart().showModal();
});

document.getElementById("dlgStartCancel").addEventListener("click", () => dlgStart().close());

document.getElementById("formStart").addEventListener("submit", (e) => {
  e.preventDefault();
  currentInputKeys = [...document.querySelectorAll('input[name="startConv"]:checked')].map((i) => i.value);
  reseedIdCounter();
  const id = allocateNodeId();
  addNodeCore(id, { kind: "start" }, nextPosition());
  dlgStart().close();
  updateValidation();
});

document.getElementById("btnOpenEnd").addEventListener("click", () => {
  if (!ensureIndustrialConstraints("end")) return;
  reseedIdCounter();
  const id = allocateNodeId();
  addNodeCore(id, { kind: "end" }, nextPosition());
  updateValidation();
});

document.getElementById("btnOpenNode").addEventListener("click", async () => {
  await loadAgentsSelect();
  await loadMcpToolsSelect();
  updateDlgCtxSummary();
  document.querySelector('input[name="dlgNodeKind"][value="agent"]').checked = true;
  syncDlgNodeKindUi();
  const pt = document.getElementById("dlgPickTool");
  if (pt.options.length) {
    pt.selectedIndex = 0;
    const t = mcpTools[0];
    document.getElementById("dlgToolDesc").textContent = t.description || "";
    renderToolArgCheckboxes(pt.value);
  }
  dlgNode().showModal();
});

document.getElementById("dlgNodeCancel").addEventListener("click", () => dlgNode().close());

document.getElementById("dlgPickTool").addEventListener("change", () => {
  const name = document.getElementById("dlgPickTool").value;
  const t = mcpTools.find((x) => x.name === name);
  document.getElementById("dlgToolDesc").textContent = (t && t.description) || "";
  renderToolArgCheckboxes(name);
  validateDlgNodePreview();
});

document.getElementById("dlgPickAgent").addEventListener("change", validateDlgNodePreview);

document.getElementById("dlgNode").addEventListener("change", (e) => {
  const t = e.target;
  if (t && t.name === "dlgArg") validateDlgNodePreview();
});

document.getElementById("formNode").addEventListener("submit", (e) => {
  e.preventDefault();
  const kind = [...document.querySelectorAll('input[name="dlgNodeKind"]')].find((r) => r.checked)?.value || "agent";
  reseedIdCounter();
  const id = allocateNodeId();
  if (kind === "agent") {
    const ak = document.getElementById("dlgPickAgent").value;
    if (!ak) {
      alert("请选择 Agent");
      return;
    }
    addNodeCore(id, { kind: "agent", agentKey: ak }, nextPosition());
    dlgNode().close();
    updateValidation();
    return;
  }
  const tn = document.getElementById("dlgPickTool").value;
  if (!tn) {
    alert("请选择工具");
    return;
  }
  const argKeys = getCheckedKeys("dlgArg");
  const t = mcpTools.find((x) => x.name === tn);
  const { miss } = toolSchemaCheck(t && t.inputSchema, argKeys);
  if (miss.length) {
    alert("请先勾选或补全必选入参: " + miss.join(", "));
    return;
  }
  addNodeCore(
    id,
    {
      kind: "tool",
      toolName: tn,
      argKeys: argKeys.length ? argKeys : ["task"],
      flattenOutput: true,
    },
    nextPosition()
  );
  dlgNode().close();
  updateValidation();
});

document.getElementById("btnFit").addEventListener("click", () => {
  if (network) network.fit({ animation: { duration: 280, easingFunction: "easeInOutQuad" } });
});

document.getElementById("btnResetView").addEventListener("click", () => {
  if (!network) return;
  network.moveTo({ scale: 1, animation: { duration: 200 } });
  network.fit({ animation: { duration: 280, easingFunction: "easeInOutQuad" } });
});

document.getElementById("btnAutoLayout").addEventListener("click", () => {
  autoLayoutDAG();
});

document.getElementById("btnDelSel").addEventListener("click", () => {
  if (!network) return;
  const sn = network.getSelectedNodes();
  const se = network.getSelectedEdges();
  if (sn.length) {
    sn.forEach((nid) => delete nodeMeta[nid]);
    nodes.remove(sn);
  }
  if (se.length) edges.remove(se);
  reseedIdCounter();
  rebuildEntrySelect();
  document.getElementById("inspBody").style.display = "none";
  document.getElementById("inspEdge").style.display = "none";
  document.getElementById("inspHint").style.display = "block";
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Delete" || e.key === "Backspace") {
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
    document.getElementById("btnDelSel").click();
  }
});

document.getElementById("btnLint").addEventListener("click", async () => {
  const payload = buildGraphForSave();
  if (!payload) return;
  const r = await fetch("/ptagent-admin/api/graph/lint", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ graph: payload.graph }),
  });
  const d = await r.json();
  const el = document.getElementById("validationBanner");
  const parts = [];
  if (d.ok) parts.push("✓ 后端结构校验通过");
  else parts.push("✗ " + (d.errors || []).join("；"));
  if ((d.warnings || []).length) parts.push("⚠ " + (d.warnings || []).join(" "));
  el.textContent = parts.join(" · ");
  el.className = d.ok && !(d.warnings || []).length ? "validation-banner ok" : "validation-banner bad";
});

function buildGraphForSave() {
  const tk = document.getElementById("selTeam").value;
  if (!tk) {
    alert("请选择 Team");
    return null;
  }
  const entry = getGraphEntry();
  const nodeList = nodes.getIds().map((id) => graphNodePayload(id));
  const industrial = nodeList.some((n) => n.kind && n.kind !== "agent");
  const edgeList = edges.get().map((e) => ({ from: e.from, to: e.to }));
  /** @type {any} */
  const graph = { entry, nodes: nodeList, edges: edgeList, linear_order: [] };
  if (industrial) {
    graph.schemaVersion = 2;
    graph.inputKeys = [...currentInputKeys];
    graph.outputKeys = inferDefaultOutputKeys();
  }
  return { tk, graph, industrial, nodeList };
}

async function loadTeamGraph(tk) {
  if (!tk) return;
  const r = await fetch(`/ptagent-admin/api/teams/${encodeURIComponent(tk)}`);
  const d = await r.json();
  const team = d.team;
  nodes.clear();
  edges.clear();
  nodeMeta = {};
  nodeIdCounter = 0;
  const g = team.graph;
  const industrial = g && (g.schemaVersion === 2 || (g.nodes || []).some((n) => n.kind && n.kind !== "agent"));

  if (g && g.nodes && g.nodes.length && industrial) {
    syncGraphKeysFromTeam(g);
    let i = 0;
    for (const n of g.nodes) {
      const id = n.id;
      nodeMeta[id] = {
        kind: n.kind || "agent",
        agentKey: n.agentKey,
        toolName: n.toolName,
        argKeys: n.argKeys,
        outputKey: n.outputKey,
        flattenOutput: n.flattenOutput !== false,
      };
      nodes.add({
        id,
        label: nodeLabel(id),
        color: COLORS[n.kind] || COLORS.legacy,
        x: 80 + (i % 4) * 180,
        y: 80 + Math.floor(i / 4) * 110,
      });
      syncNodeVisual(id);
      i++;
    }
    for (const e of g.edges || []) {
      edges.add({ from: e.from, to: e.to });
    }
  } else if (g && g.nodes && g.nodes.length) {
    let i = 0;
    for (const n of g.nodes) {
      const id = n.id;
      const ak = n.agentKey;
      nodeMeta[id] = { kind: "agent", agentKey: ak };
      nodes.add({
        id,
        label: nodeLabel(id),
        color: COLORS.agent,
        x: 80 + (i % 4) * 160,
        y: 80 + Math.floor(i / 4) * 100,
      });
      syncNodeVisual(id);
      i++;
    }
    for (const e of g.edges || []) {
      edges.add({ from: e.from, to: e.to });
    }
  } else {
    const lo = team.linear_order || [];
    lo.forEach((ak, j) => {
      const id = `n${j}`;
      nodeMeta[id] = { kind: "agent", agentKey: ak };
      nodes.add({
        id,
        label: nodeLabel(id),
        color: COLORS.agent,
        x: 80 + j * 160,
        y: 120,
      });
      syncNodeVisual(id);
      if (j > 0) edges.add({ from: `n${j - 1}`, to: id });
    });
  }
  reseedIdCounter();
  rebuildEntrySelect();
  if (network) network.fit({ animation: false });
  updateValidation();
  syncTeamTableHighlight();
}

document.getElementById("btnLoad").addEventListener("click", () => {
  const tk = document.getElementById("selTeam").value;
  if (!tk) return alert("请在下拉或列表中选择 Team");
  loadTeamGraph(tk);
});

document.getElementById("btnSave").addEventListener("click", async () => {
  const pack = buildGraphForSave();
  if (!pack) return;
  const { tk, graph, industrial, nodeList } = pack;
  if (industrial) {
    if (countKind("start") !== 1 || countKind("end") !== 1) return alert("工业编排需要恰好 1 个起点与 1 个结束节点");
    const ge = getGraphEntry();
    if (!nodeList.find((n) => n.id === ge && n.kind === "start")) {
      return alert("工业编排需有唯一起点（kind=start），且数据流入口对应该节点");
    }
  } else {
    if (nodeList.some((n) => !n.agentKey)) return alert("每个节点需要 agentKey（旧版链）");
  }
  const res = await fetch(`/ptagent-admin/api/teams/${encodeURIComponent(tk)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: tk, name: "", graph, linear_order: [] }),
  });
  if (!res.ok) return alert(await res.text());
  alert("已保存");
  loadTeamSelect();
});

document.getElementById("btnNewTeam").addEventListener("click", () => {
  const k = prompt("Team key");
  if (!k) return;
  const key = k.trim();
  fetch(`/ptagent-admin/api/teams/${encodeURIComponent(key)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, name: "", graph: null, linear_order: [] }),
  }).then(async (r) => {
    if (!r.ok) return alert(r.statusText);
    await loadTeamSelect();
    document.getElementById("selTeam").value = key;
    syncTeamTableHighlight();
    nodes.clear();
    edges.clear();
    nodeMeta = {};
    nodeIdCounter = 0;
    currentInputKeys = [];
    rebuildEntrySelect();
  });
});

function syncTeamTableHighlight() {
  const cur = document.getElementById("selTeam").value;
  document.querySelectorAll("#teamTableBody tr").forEach((tr) => {
    tr.classList.toggle("team-row-current", tr.getAttribute("data-team-key") === cur);
  });
}

async function loadTeamSelect() {
  const r = await fetch("/ptagent-admin/api/teams");
  const d = await r.json();
  const teams = d.teams || [];
  const prevSel = document.getElementById("selTeam").value;
  const sel = document.getElementById("selTeam");
  sel.innerHTML = "";
  for (const t of teams) {
    const o = document.createElement("option");
    o.value = t.key;
    o.textContent = t.key + (t.name ? ` — ${t.name}` : "");
    sel.appendChild(o);
  }
  if (prevSel && teams.some((x) => x.key === prevSel)) sel.value = prevSel;

  const tbody = document.getElementById("teamTableBody");
  if (!tbody) return;
  if (!teams.length) {
    tbody.innerHTML = `<tr><td colspan="3" class="muted">暂无 Team，点击「新建」创建。</td></tr>`;
    return;
  }
  tbody.innerHTML = teams
    .map(
      (t) =>
        `<tr data-team-key="${escapeAttr(t.key)}">
        <td><code>${escapeHtml(t.key)}</code></td>
        <td>${escapeHtml(t.name || "—")}</td>
        <td class="team-col-actions">
          <button type="button" class="btn btn-sm team-load" data-team="${escapeAttr(t.key)}">加载画布</button>
          <button type="button" class="btn btn-sm team-pick" data-team="${escapeAttr(t.key)}">选中</button>
          <button type="button" class="btn btn-sm team-del" data-team="${escapeAttr(t.key)}">删除</button>
        </td>
      </tr>`
    )
    .join("");

  tbody.querySelectorAll(".team-load").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const key = btn.getAttribute("data-team");
      if (!key) return;
      document.getElementById("selTeam").value = key;
      syncTeamTableHighlight();
      await loadTeamGraph(key);
    });
  });
  tbody.querySelectorAll(".team-pick").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.getAttribute("data-team");
      if (!key) return;
      document.getElementById("selTeam").value = key;
      syncTeamTableHighlight();
    });
  });
  tbody.querySelectorAll(".team-del").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const key = btn.getAttribute("data-team");
      if (!key || !confirm(`删除 Team「${key}」？不可恢复。`)) return;
      const res = await fetch(`/ptagent-admin/api/teams/${encodeURIComponent(key)}`, { method: "DELETE" });
      if (!res.ok) return alert(await res.text());
      const wasCurrent = document.getElementById("selTeam").value === key;
      await loadTeamSelect();
      if (wasCurrent) {
        nodes.clear();
        edges.clear();
        nodeMeta = {};
        nodeIdCounter = 0;
        currentInputKeys = [];
        rebuildEntrySelect();
        if (network) network.fit({ animation: false });
        document.getElementById("inspBody").style.display = "none";
        document.getElementById("inspHint").style.display = "block";
      }
      updateValidation();
    });
  });
  syncTeamTableHighlight();
}

document.getElementById("selTeam").addEventListener("change", syncTeamTableHighlight);

async function boot() {
  await loadFieldCatalog();
  initNet();
  await loadMcpToolsSelect();
  await loadTeamSelect();
  refreshEdgeList();
  updateValidation();
}

boot();
