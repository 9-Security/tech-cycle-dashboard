/* Shared helpers for all dashboard pages. */
(function (global) {
  const num = (x) => x != null && !Number.isNaN(Number(x));
  const fmt = (x, d = 2) => (num(x) ? Number(x).toFixed(d) : "—");
  const pct = (x, d = 1) => (num(x) ? (Number(x) * 100).toFixed(d) + "%" : "—");
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function loadJSON(path) {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(path + " → " + res.status);
    return res.json();
  }

  function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  /* Live/stale banner driven by health.json. */
  function renderBanner(health) {
    const el = document.getElementById("banner");
    if (!el || !health) return;
    const runAt = health.run_at ? new Date(health.run_at) : null;
    const ageDays = runAt ? (Date.now() - runAt.getTime()) / 86400000 : Infinity;
    const stale = ageDays > 4;
    el.classList.toggle("stale", stale);
    el.classList.toggle("live", !stale);
    const warn = (health.checks || []).filter((c) => c.status !== "PASS").length;
    el.innerHTML =
      "<strong>" + (stale ? "Stale data." : "Live data.") + "</strong> " +
      "Last refresh " + esc(health.run_at || "—") +
      " · market data through <strong>" + esc(health.data_through || "—") + "</strong>" +
      " · monthly panel through " + esc(health.panel_end || "—") +
      " · DQ " + ((health.checks || []).length - warn) + "/" + (health.checks || []).length + " pass" +
      (stale ? " · the daily refresh has not succeeded for " + Math.floor(ageDays) + " days." : "");
  }

  function regimeBadge(r) {
    if (!r) return "—";
    return '<span class="badge r' + esc(r.code) + '">' + esc(r.label) + "</span>";
  }

  function chartDefaults() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
      scales: {
        x: { ticks: { maxTicksLimit: 10, color: "#6b6560", font: { size: 10 } }, grid: { color: "#eee8de" } },
        y: { ticks: { color: "#6b6560", font: { size: 10 } }, grid: { color: "#eee8de" } },
      },
    };
  }

  global.TCD = { num, fmt, pct, esc, loadJSON, setText, renderBanner, regimeBadge, chartDefaults };
})(window);
