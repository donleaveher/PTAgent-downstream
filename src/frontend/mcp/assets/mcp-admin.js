(function () {
  const API = "/mcp-admin/api";

  const ARG_PRESETS = {
    normalize_peptide: { peptide: "AM(ox)K", charge: 1 },
    peptide_mass_and_mz: { token_ids_with_ptm: [6, 34, 15], charge: 2 },
    token_ids_to_peptide_strings: { token_ids_with_ptm: [6, 34, 15] },
  };

  function el(id) {
    return document.getElementById(id);
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function setPill(ok, text) {
    const p = el("statusPill");
    if (!p) return;
    p.innerHTML = `<span class="pill ${ok ? "ok" : "bad"}">${escapeHtml(text)}</span>`;
  }

  function normMcpPath(p) {
    const s = (p || "").replace(/\/$/, "") || "/mcp-admin";
    return s === "/mcp-admin" ? "/mcp-admin" : s;
  }

  function navMarkActive() {
    const here = normMcpPath(window.location.pathname);
    document.querySelectorAll(".mcp-nav a").forEach((a) => {
      try {
        const u = new URL(a.getAttribute("href"), window.location.origin);
        const p = normMcpPath(u.pathname);
        if (p === here) a.classList.add("active");
      } catch (_) {}
    });
  }

  async function fetchOverview() {
    const r = await fetch(`${API}/overview`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  function renderOverview(data) {
    const g = el("overviewGrid");
    const hint = el("overviewHint");
    if (!g) return;
    const items = [
      ["配置 endpoint", data.endpoint],
      ["HTTP MCP URL", data.httpMcpUrl || "—"],
      ["Provider WS URL", data.providerWsUrl || "—"],
      ["mcpMode", data.mode],
      ["mcpVersion", data.version],
      ["自动拉起子进程", data.autoStartSubprocess ? "是" : "否"],
      ["PID 文件", data.subprocessPidFile],
      ["Broker 可达", data.reachable ? "是" : "否"],
      ["工具数量", data.toolCount != null ? String(data.toolCount) : "—"],
    ];
    g.innerHTML = items
      .map(
        ([k, v]) => `
        <div class="card">
          <div class="label">${escapeHtml(k)}</div>
          <div class="val">${escapeHtml(String(v))}</div>
        </div>`
      )
      .join("");
    setPill(data.reachable, data.reachable ? "Broker 可达" : "Broker 不可达");
    if (hint) hint.textContent = data.lastError ? `最近错误：${data.lastError}` : "";
  }

  function exampleArgsForTool(name) {
    if (!name) return null;
    if (ARG_PRESETS[name] != null) return ARG_PRESETS[name];
    const short = name.includes("__") ? name.split("__").pop() : name;
    if (ARG_PRESETS[short] != null) return ARG_PRESETS[short];
    return null;
  }

  function toolSortKey(t) {
    const c = t.categoryId || "\uFFFF";
    const g = t.groupId || "\uFFFF";
    const n = t.name || "";
    return `${c}\0${g}\0${n}`;
  }

  async function loadConventionsInto(preId) {
    const pre = el(preId || "conventionsPre");
    if (!pre) return;
    try {
      const r = await fetch(`${API}/conventions`);
      if (!r.ok) {
        pre.textContent = await r.text();
        return;
      }
      const doc = await r.json();
      pre.textContent = JSON.stringify(doc, null, 2);
    } catch (e) {
      pre.textContent = String(e);
    }
  }

  async function loadToolsIntoTable() {
    const err = el("toolsErr");
    if (err) err.hidden = true;
    const tbody = el("toolRows");
    if (tbody) tbody.innerHTML = "";
    const r = await fetch(`${API}/tools`);
    if (!r.ok) {
      const t = await r.text();
      if (err) {
        err.textContent = t;
        err.hidden = false;
      }
      return;
    }
    const data = await r.json();
    const tools = (data.tools || []).slice().sort((a, b) => toolSortKey(a).localeCompare(toolSortKey(b)));
    if (!tbody) return;
    const sel = el("toolSelect");
    if (sel) {
      sel.innerHTML = "";
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "— 选择工具 —";
      sel.appendChild(placeholder);
    }

    const byGroup = new Map();
    tools.forEach((t) => {
      const gl = `${t.categoryTitle || "未分类"} — ${t.groupLabel || "未分组"}`;
      if (!byGroup.has(gl)) byGroup.set(gl, []);
      byGroup.get(gl).push(t);
    });

    let lastHeader = null;
    tools.forEach((t) => {
      const header = `${t.categoryTitle || "未分类"} — ${t.groupLabel || "未分组"}`;
      if (header !== lastHeader) {
        lastHeader = header;
        const tr = document.createElement("tr");
        tr.className = "group-row";
        tr.innerHTML = `<td colspan="3"><strong>${escapeHtml(header)}</strong></td>`;
        tbody.appendChild(tr);
      }
      const tr = document.createElement("tr");
      tr.innerHTML = `
          <td><strong>${escapeHtml(t.name)}</strong></td>
          <td class="desc">${escapeHtml(t.description || "")}</td>
          <td>
            <details>
              <summary>查看</summary>
              <pre>${escapeHtml(JSON.stringify(t.inputSchema || {}, null, 2))}</pre>
            </details>
          </td>`;
      tbody.appendChild(tr);
    });

    if (sel) {
      byGroup.forEach((list, label) => {
        const og = document.createElement("optgroup");
        og.label = label;
        list.forEach((t) => {
          const o = document.createElement("option");
          o.value = t.name;
          o.textContent = t.name;
          og.appendChild(o);
        });
        sel.appendChild(og);
      });
    }
  }

  async function callTool() {
    const err = el("callErr");
    if (err) err.hidden = true;
    const name = el("toolSelect").value;
    if (!name) {
      if (err) {
        err.textContent = "请选择工具";
        err.hidden = false;
      }
      return;
    }
    let args;
    try {
      args = JSON.parse(el("argsJson").value || "{}");
      if (args === null || typeof args !== "object" || Array.isArray(args)) {
        throw new Error("参数必须是 JSON 对象");
      }
    } catch (e) {
      if (err) {
        err.textContent = "参数 JSON 无效：" + e.message;
        err.hidden = false;
      }
      return;
    }
    const r = await fetch(`${API}/tools/call`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, arguments: args }),
    });
    const out = el("callResult");
    if (!r.ok) {
      const raw = await r.text();
      let display = raw;
      try {
        const j = JSON.parse(raw);
        if (j && typeof j === "object") display = JSON.stringify(j, null, 2);
      } catch (_) {}
      out.textContent = display;
      if (err) {
        err.textContent = "调用失败（HTTP " + r.status + "）；见上方 JSON（含 detail）";
        err.hidden = false;
      }
      return;
    }
    const data = await r.json();
    out.textContent = JSON.stringify(data.result, null, 2);
  }

  async function debugFetch(label, url, preId) {
    const pre = el(preId);
    if (!pre) return;
    pre.textContent = "加载中…";
    try {
      const r = await fetch(url);
      const txt = await r.text();
      let display = txt;
      try {
        const j = JSON.parse(txt);
        if (j && typeof j === "object") display = JSON.stringify(j, null, 2);
      } catch (_) {}
      pre.textContent = display;
    } catch (e) {
      pre.textContent = String(e);
    }
  }

  function initIndex() {
    const btn = el("btnRefresh");
    if (btn) {
      btn.addEventListener("click", async () => {
        try {
          const o = await fetchOverview();
          renderOverview(o);
        } catch (e) {
          const hint = el("overviewHint");
          if (hint) hint.textContent = "加载失败：" + e.message;
        }
      });
    }
    fetchOverview()
      .then(renderOverview)
      .catch((e) => {
        const hint = el("overviewHint");
        if (hint) hint.textContent = "加载失败：" + e.message;
        setPill(false, "加载失败");
      });
  }

  function initTools() {
    el("btnLoadTools")?.addEventListener("click", () =>
      loadToolsIntoTable().catch((e) => {
        const te = el("toolsErr");
        if (te) {
          te.textContent = String(e);
          te.hidden = false;
        }
      })
    );
    el("btnCall")?.addEventListener("click", () =>
      callTool().catch((e) => {
        const ce = el("callErr");
        if (ce) {
          ce.textContent = String(e);
          ce.hidden = false;
        }
      })
    );
    el("btnFillExample")?.addEventListener("click", () => {
      const name = el("toolSelect").value;
      const ex = exampleArgsForTool(name);
      const cerr = el("callErr");
      if (cerr) cerr.hidden = true;
      if (!name) {
        if (cerr) {
          cerr.textContent = "请先选择工具";
          cerr.hidden = false;
        }
        return;
      }
      if (!ex) {
        if (cerr) {
          cerr.textContent = "暂无该工具的内置示例，请根据上方 Schema 手写 JSON。";
          cerr.hidden = false;
        }
        return;
      }
      el("argsJson").value = JSON.stringify(ex, null, 2);
    });
  }

  function initFields() {
    loadConventionsInto("conventionsPre");
  }

  function initDebug() {
    initIndex();
    el("btnFetchOverviewJson")?.addEventListener("click", () =>
      debugFetch("ov", `${API}/overview`, "debugOverviewJson")
    );
    el("btnFetchToolsJson")?.addEventListener("click", () =>
      debugFetch("tools", `${API}/tools`, "debugToolsJson")
    );
    el("btnFetchCatalogJson")?.addEventListener("click", () =>
      debugFetch("cat", `${API}/tool-catalog`, "debugCatalogJson")
    );
    el("btnFetchConventionsJson")?.addEventListener("click", () =>
      debugFetch("conv", `${API}/conventions`, "debugConventionsJson")
    );
    el("btnFetchAllDebug")?.addEventListener("click", async () => {
      await debugFetch("", `${API}/overview`, "debugOverviewJson");
      await debugFetch("", `${API}/tools`, "debugToolsJson");
      await debugFetch("", `${API}/tool-catalog`, "debugCatalogJson");
      await debugFetch("", `${API}/conventions`, "debugConventionsJson");
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    navMarkActive();
    const page = document.body.getAttribute("data-page") || "";
    if (page === "index") initIndex();
    else if (page === "tools") initTools();
    else if (page === "fields") initFields();
    else if (page === "debug") initDebug();
  });
})();
