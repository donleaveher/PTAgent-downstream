async function load() {
  try {
    const r = await fetch("/ptagent-admin/api/overview");
    const d = await r.json();
    const el = document.getElementById("meta");
    if (el) {
      el.textContent = `注册表: ${d.registryPath} · Agent: ${d.agentCount} · Team: ${d.teamCount}`;
    }
  } catch (_) {}
}
load();
