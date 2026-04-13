async function loadOverview() {
  const pill = document.getElementById("statusPill");
  const grid = document.getElementById("categoryGrid");
  const hint = document.getElementById("overviewHint");
  pill.textContent = "加载中…";
  pill.className = "";
  grid.innerHTML = "";
  hint.textContent = "";

  try {
    const res = await fetch("/agent-studio/api/overview");
    const data = await res.json();
    if (data.ok) {
      pill.textContent = `MCP 已连接 · ${data.toolCount} 个工具`;
      pill.className = "ok";
    } else {
      pill.textContent = "MCP 不可用";
      pill.className = "err";
      hint.textContent = data.error || "无法列出工具（请确认 Broker 已启动）。";
    }

    const map = data.toolsByCategory || {};
    const keys = Object.keys(map).sort();
    if (!keys.length && data.ok) {
      hint.textContent = "当前无工具注册。";
      return;
    }
    for (const cat of keys) {
      const names = map[cat] || [];
      const block = document.createElement("div");
      block.className = "cat-block";
      const h = document.createElement("h3");
      h.textContent = cat;
      block.appendChild(h);
      const ul = document.createElement("ul");
      for (const n of names) {
        const li = document.createElement("li");
        li.textContent = n;
        ul.appendChild(li);
      }
      block.appendChild(ul);
      grid.appendChild(block);
    }
  } catch (e) {
    pill.textContent = "请求失败";
    pill.className = "err";
    hint.textContent = String(e);
  }
}

document.getElementById("btnRefresh")?.addEventListener("click", loadOverview);
loadOverview();
