(function () {
  const KEY = "ptagentSidebarCollapsed";
  function apply() {
    document.body.classList.toggle("ptagent-sidebar-collapsed", localStorage.getItem(KEY) === "1");
  }
  function collapseFromMain() {
    if (localStorage.getItem(KEY) === "1") return;
    localStorage.setItem(KEY, "1");
    apply();
  }
  function init() {
    apply();
    const btn = document.getElementById("btnSidebarToggle");
    if (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        const collapsed = localStorage.getItem(KEY) === "1";
        localStorage.setItem(KEY, collapsed ? "" : "1");
        apply();
      });
    }
    document.querySelectorAll(".layout-main-column").forEach((col) => {
      col.addEventListener("click", function (e) {
        if (e.target.closest("#btnSidebarToggle")) return;
        collapseFromMain();
      });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
