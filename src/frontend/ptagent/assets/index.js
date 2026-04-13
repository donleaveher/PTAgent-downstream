async function load() {
  try {
    const [ov, mcp] = await Promise.all([
      fetch("/ptagent-admin/api/overview").then((r) => r.json()),
      fetch("/ptagent-admin/api/mcp-resources").then((r) => r.json()),
    ]);
    document.getElementById("stAgents").textContent = ov.agentCount;
    document.getElementById("stTeams").textContent = ov.teamCount;
    document.getElementById("stTools").textContent = mcp.ok ? mcp.tools.length : "—";
    document.getElementById("stPath").textContent = `注册表: ${ov.registryPath} · MCP: ${ov.mcpEndpoint}`;
  } catch (e) {
    document.getElementById("stPath").textContent = String(e);
  }
}
load();
