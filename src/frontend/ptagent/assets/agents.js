let mcpData = { byCategory: {}, tools: [] };
let agentList = [];
let selectedKey = null;

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

async function loadMcp() {
  const r = await fetch("/ptagent-admin/api/mcp-resources");
  mcpData = await r.json();
  renderToolPick();
}

function renderToolPick() {
  const el = document.getElementById("toolPick");
  el.innerHTML = "";
  const bc = mcpData.byCategory || {};
  for (const [cat, items] of Object.entries(bc)) {
    const block = document.createElement("div");
    block.className = "cat-block";
    const t = document.createElement("div");
    t.className = "cat-title";
    t.textContent = cat;
    block.appendChild(t);
    for (const tool of items) {
      const lab = document.createElement("label");
      lab.className = "chk";
      const inp = document.createElement("input");
      inp.type = "checkbox";
      inp.name = "tool";
      inp.value = tool.name;
      inp.dataset.category = tool.tool_category || cat;
      lab.appendChild(inp);
      lab.appendChild(document.createTextNode(` ${tool.name}`));
      block.appendChild(lab);
    }
    el.appendChild(block);
  }
}

function getCheckedTools() {
  return [...document.querySelectorAll('#toolPick input[name="tool"]:checked')].map((x) => x.value);
}

function setChecksFromRecord(rec) {
  document.querySelectorAll('#toolPick input[name="tool"]').forEach((inp) => {
    inp.checked = false;
  });
  const al = rec.mcp_tool_allowlist;
  const cats = rec.mcp_categories;
  if (al && al.length) {
    const set = new Set(al);
    document.querySelectorAll('#toolPick input[name="tool"]').forEach((inp) => {
      if (set.has(inp.value)) inp.checked = true;
    });
  } else if (cats && cats.length) {
    const cs = new Set(cats);
    document.querySelectorAll('#toolPick input[name="tool"]').forEach((inp) => {
      if (cs.has((inp.dataset.category || "").trim())) inp.checked = true;
    });
  }
}

function renderCards() {
  const root = document.getElementById("cardRoot");
  root.innerHTML = "";
  for (const a of agentList) {
    const div = document.createElement("div");
    div.className = "agent-card" + (selectedKey === a.key ? " selected" : "");
    const n = (a.mcp_tool_allowlist || []).length;
    const c = (a.mcp_categories || []).length;
    const hint =
      n > 0
        ? `工具白名单 ${n} 个`
        : c > 0
          ? `类别 ${c} 个`
          : "不限制工具";
    const lm = a.llm_model || "gpt-4o-mini";
    div.innerHTML = `<div class="agent-card-top">
      <h3>${escapeHtml(a.key)}</h3>
      <button type="button" class="btn btn-sm agent-card-del" data-agent-key="${escapeAttr(a.key)}">删除</button>
    </div>
    <div class="meta">${escapeHtml(a.name || "")} · ${escapeHtml(hint)} · ${escapeHtml(lm)}</div>`;
    div.addEventListener("click", (ev) => {
      if (ev.target.closest(".agent-card-del")) return;
      selectedKey = a.key;
      document.querySelectorAll(".agent-card").forEach((x) => x.classList.remove("selected"));
      div.classList.add("selected");
      document.getElementById("btnRun").disabled = false;
      document.getElementById("btnVal").disabled = false;
    });
    div.addEventListener("dblclick", (e) => {
      if (e.target.closest(".agent-card-del")) return;
      e.stopPropagation();
      openEditor(a);
    });
    root.appendChild(div);
  }
}

async function loadAgents() {
  const r = await fetch("/ptagent-admin/api/agents");
  const d = await r.json();
  agentList = d.agents || [];
  renderCards();
}

function openEditor(rec) {
  const ed = document.getElementById("editor");
  ed.style.display = "block";
  document.getElementById("edTitle").textContent = rec ? `编辑 ${rec.key}` : "新建 Agent";
  document.getElementById("fKey").value = rec?.key || "";
  document.getElementById("fKey").readOnly = !!rec;
  document.getElementById("fName").value = rec?.name || "";
  document.getElementById("fPrompt").value = rec?.system_prompt || "";
  document.getElementById("fRag").value = rec?.rag_profile_id || "";
  document.getElementById("fModel").value = rec?.llm_model || "gpt-4o-mini";
  document.getElementById("fTemp").value =
    rec?.llm_temperature !== undefined && rec?.llm_temperature !== null ? rec.llm_temperature : 0.2;
  const restrict =
    !!(rec?.mcp_tool_allowlist && rec.mcp_tool_allowlist.length) ||
    !!(rec?.mcp_categories && rec.mcp_categories.length);
  document.getElementById("fRestrict").checked = restrict;
  document.getElementById("toolPick").style.display = restrict ? "block" : "none";
  if (rec) setChecksFromRecord(rec);
  else document.querySelectorAll('#toolPick input[name="tool"]').forEach((inp) => (inp.checked = false));
}

document.getElementById("fRestrict").addEventListener("change", (e) => {
  document.getElementById("toolPick").style.display = e.target.checked ? "block" : "none";
});

document.getElementById("btnNew").addEventListener("click", () => openEditor(null));
document.getElementById("btnReload").addEventListener("click", () => loadAgents());
document.getElementById("btnCancel").addEventListener("click", () => {
  document.getElementById("editor").style.display = "none";
});

document.getElementById("btnSave").addEventListener("click", async () => {
  const key = document.getElementById("fKey").value.trim();
  if (!key) return alert("需要 key");
  const restrict = document.getElementById("fRestrict").checked;
  let mcp_tool_allowlist = null;
  let mcp_categories = null;
  if (restrict) {
    const names = getCheckedTools();
    mcp_tool_allowlist = names;
    mcp_categories = null;
  }
  let lt = parseFloat(document.getElementById("fTemp").value);
  if (Number.isNaN(lt)) lt = 0.2;
  const body = {
    key,
    name: document.getElementById("fName").value,
    description: "",
    mcp_categories,
    mcp_tool_allowlist,
    system_prompt: document.getElementById("fPrompt").value,
    rag_profile_id: document.getElementById("fRag").value || null,
    llm_model: document.getElementById("fModel").value.trim() || "gpt-4o-mini",
    llm_temperature: lt,
    meta: {},
  };
  const r = await fetch(`/ptagent-admin/api/agents/${encodeURIComponent(key)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) return alert(await r.text());
  document.getElementById("editor").style.display = "none";
  loadAgents();
});

document.getElementById("btnRun").addEventListener("click", async () => {
  const out = document.getElementById("runOut");
  out.textContent = "…";
  const r = await fetch("/ptagent-admin/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target: "agent",
      key: selectedKey,
      task: document.getElementById("runTask").value || "test",
      model: (() => {
        const m = document.getElementById("runModel").value.trim();
        return m || null;
      })(),
      temperature: (() => {
        const t = document.getElementById("runTemp").value;
        if (t === "" || t === undefined) return null;
        const x = parseFloat(t);
        return Number.isNaN(x) ? null : x;
      })(),
    }),
  });
  out.textContent = JSON.stringify(await r.json(), null, 2);
});

document.getElementById("btnVal").addEventListener("click", async () => {
  const out = document.getElementById("runOut");
  out.textContent = "…";
  const r = await fetch(`/ptagent-admin/api/agents/${encodeURIComponent(selectedKey)}/debug/validate`, {
    method: "POST",
  });
  out.textContent = JSON.stringify(await r.json(), null, 2);
});

document.getElementById("cardRoot").addEventListener("click", async (e) => {
  const del = e.target.closest(".agent-card-del");
  if (!del) return;
  e.stopPropagation();
  const key = del.getAttribute("data-agent-key");
  if (!key || !confirm(`删除 Agent「${key}」？不可恢复。`)) return;
  const r = await fetch(`/ptagent-admin/api/agents/${encodeURIComponent(key)}`, { method: "DELETE" });
  if (!r.ok) return alert(await r.text());
  if (selectedKey === key) {
    selectedKey = null;
    document.getElementById("btnRun").disabled = true;
    document.getElementById("btnVal").disabled = true;
  }
  loadAgents();
});

loadMcp().then(loadAgents);
