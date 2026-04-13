function setStatus(modelId, text, ok) {
  const el = document.getElementById(`st-${cssEscape(modelId)}`);
  if (!el) return;
  el.textContent = text;
  el.className = ok === true ? "pill ok" : ok === false ? "pill bad" : "";
}

function cssEscape(s) {
  return encodeURIComponent(String(s)).replace(/%/g, "_");
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

function syncLlmTableMirrors() {
  const baseInp = document.getElementById("fBase");
  const keyInp = document.getElementById("fKey");
  const baseRaw = (baseInp && baseInp.value.trim()) || "";
  const keyRaw = keyInp ? String(keyInp.value) : "";
  const baseShow = baseRaw || "（默认 https://api.openai.com/v1）";
  const keyShow = keyRaw || "（未填写：留空保存则沿用已写入文件/环境变量）";
  document.querySelectorAll("#modelRows .llm-sync-base").forEach((td) => {
    td.textContent = baseShow;
    td.title = baseRaw || "默认官方 Base";
  });
  document.querySelectorAll("#modelRows .llm-sync-key").forEach((td) => {
    td.textContent = keyShow.length > 120 ? keyShow.slice(0, 120) + "…" : keyShow;
    td.title = keyRaw || "未在输入框中填写";
  });
}

function focusConnectionEditors() {
  const base = document.getElementById("fBase");
  const key = document.getElementById("fKey");
  if (base) {
    base.scrollIntoView({ behavior: "smooth", block: "center" });
    base.focus();
  }
  if (key) setTimeout(() => key.focus(), 300);
}

async function loadSettings() {
  const r = await fetch("/ptagent-admin/api/llm/settings");
  const d = await r.json();
  document.getElementById("fBase").value = d.openai_api_base || "";
  const pk = d.openai_api_key;
  document.getElementById("fKey").value = pk != null && pk !== undefined ? String(pk) : "";
  document.getElementById("keyHint").textContent = d.has_api_key
    ? `当前已配置密钥（脱敏尾缀：${d.api_key_tail || "****"}）；上表与输入框中为完整 Key，可编辑后点保存。`
    : "当前未检测到有效密钥；可在上方填写并保存，或使用环境变量 OPENAI_API_KEY / PTAGENT_OPENAI_API_KEY。";
  document.getElementById("pathNote").textContent = d.source_note + " · " + (d.overridesPath || "");
  syncLlmTableMirrors();
}

async function loadModels() {
  const r = await fetch("/ptagent-admin/api/llm/models");
  const d = await r.json();
  const tbody = document.getElementById("modelRows");
  tbody.innerHTML = "";
  for (const m of d.models || []) {
    const id = m.id;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><code>${escapeHtml(id)}</code></td>
      <td>${escapeHtml(m.label || "")} <span class="muted">(${escapeHtml(m.provider || "")})</span></td>
      <td class="llm-cell-sync llm-sync-base muted small"></td>
      <td class="llm-cell-sync llm-sync-key mono small"></td>
      <td id="st-${cssEscape(id)}">—</td>
      <td class="td-actions"><button type="button" class="btn btn-sm btn-ping-one" data-model="${escapeAttr(id)}">测试</button>
      <button type="button" class="btn btn-sm llm-row-edit">改连接</button></td>`;
    tbody.appendChild(tr);
  }
  tbody.querySelectorAll(".btn-ping-one").forEach((btn) => {
    btn.addEventListener("click", () => pingOne(btn.getAttribute("data-model")));
  });
  tbody.querySelectorAll(".llm-row-edit").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      focusConnectionEditors();
    });
  });
  syncLlmTableMirrors();
}

async function pingOne(modelId) {
  const msg = document.getElementById("tMsg").value || "ping";
  setStatus(modelId, "…", undefined);
  const r = await fetch("/ptagent-admin/api/llm/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: modelId, message: msg }),
  });
  const d = await r.json();
  if (d.ok) {
    const prev = (d.reply_preview || "").slice(0, 80);
    setStatus(modelId, `OK · ${prev}`, true);
  } else {
    setStatus(modelId, (d.error || "error").slice(0, 120), false);
  }
}

document.getElementById("btnReload").addEventListener("click", () => {
  loadSettings();
  loadModels();
});

document.getElementById("btnSave").addEventListener("click", async () => {
  const body = {
    openai_api_base: document.getElementById("fBase").value.trim() || null,
  };
  const k = document.getElementById("fKey").value;
  if (k !== "") body.openai_api_key = k;
  const r = await fetch("/ptagent-admin/api/llm/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const d = await r.json();
  if (!r.ok) return alert(JSON.stringify(d));
  alert("已保存");
  loadSettings();
});

document.getElementById("btnClearKey").addEventListener("click", async () => {
  if (!confirm("确定清除 data/llm_overrides.json 中的密钥覆盖？（将回退到环境变量）")) return;
  const r = await fetch("/ptagent-admin/api/llm/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ openai_api_key: "" }),
  });
  const d = await r.json();
  if (!r.ok) return alert(JSON.stringify(d));
  alert("已清除");
  loadSettings();
});

document.getElementById("btnTest").addEventListener("click", async () => {
  const out = document.getElementById("testOut");
  out.textContent = "…";
  const r = await fetch("/ptagent-admin/api/llm/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: document.getElementById("tModel").value.trim() || "gpt-4o-mini",
      message: document.getElementById("tMsg").value || "ping",
    }),
  });
  out.textContent = JSON.stringify(await r.json(), null, 2);
});

document.getElementById("btnPingAll").addEventListener("click", async () => {
  const out = document.getElementById("testOut");
  out.textContent = "批量探测中…";
  const r = await fetch("/ptagent-admin/api/llm/ping-all", { method: "POST" });
  const d = await r.json();
  out.textContent = JSON.stringify(d, null, 2);
  for (const row of d.results || []) {
    const mid = row.id;
    if (row.ok) {
      const prev = (row.reply_preview || "").slice(0, 80);
      setStatus(mid, `OK · ${prev}`, true);
    } else {
      setStatus(mid, (row.error || "err").slice(0, 120), false);
    }
  }
});

["fBase", "fKey"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("input", syncLlmTableMirrors);
});

loadSettings();
loadModels();
