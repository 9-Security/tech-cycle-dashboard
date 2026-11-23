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

  const T = () => window.TCD_I18N;

  /* Live/stale banner driven by health.json. */
  function renderBanner(health) {
    const el = document.getElementById("banner");
    if (!el || !health) return;
    const t = T().t;
    const runAt = health.run_at ? new Date(health.run_at) : null;
    const ageDays = runAt ? (Date.now() - runAt.getTime()) / 86400000 : Infinity;
    const stale = ageDays > 4;
    el.classList.toggle("stale", stale);
    el.classList.toggle("live", !stale);
    const checks = health.checks || [];
    const pass = checks.filter((c) => c.status === "PASS").length;
    el.innerHTML = "<strong>" + t(stale ? "banner.stale" : "banner.live") + "</strong> " +
      t("banner.body", { run: esc(health.run_at || "—"), through: esc(health.data_through || "—"), panel: esc(health.panel_end || "—"),
        pass: pass, total: checks.length }) +
      (stale ? t("banner.staleNote", { days: Math.floor(ageDays) }) : "");
  }

  function regimeLabel(code, fallback) {
    const k = "regime." + code;
    return T().has(k) ? T().t(k) : fallback || "—";
  }

  function regimeBadge(r) {
    if (!r) return "—";
    return '<span class="badge r' + esc(r.code) + '">' + esc(regimeLabel(r.code, r.label)) + "</span>";
  }

  function table(id, headers, rows) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML =
      "<thead><tr>" + headers.map((h) => "<th>" + esc(h) + "</th>").join("") + "</tr></thead><tbody>" +
      rows.map((r) => "<tr>" + r.map((c) => "<td>" + c + "</td>").join("") + "</tr>").join("") + "</tbody>";
  }

  function setHTML(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }

  /* Localized scenario cards rebuilt from structured trigger data
     (scenarios.json triggers + status), so both languages share one source. */
  function buildScenarios(status, sc) {
    const t = T().t;
    const trig = {};
    (sc.triggers || []).forEach((x) => { trig[x.id] = x; });
    const src = status.provisional || status;
    const regime = regimeLabel(src.regime && src.regime.code, src.regime && src.regime.label);
    const f2 = (x) => fmt(x, 2);
    const pos = (x) => fmt(Math.max(x || 0, 0), 2);
    const out = [];
    const s = trig.shock || {}, o = trig.overheat || {}, d = trig.digestion || {};
    out.push({
      id: "base", thesis: t("sc.base.thesis", { regime: regime }),
      flips: [t("sc.base.flip.vix", { v: f2(s.value), t: f2(s.threshold) }),
              t("sc.base.flip.oh", { v: f2(o.value), t: f2(o.threshold) }),
              t("sc.base.flip.earn", { v: f2(d.value), t: f2(d.threshold) })],
      weight: (status.weights || {}).target_weight, rationale: t("sc.base.rationale"),
    });
    out.push({
      id: "overheat",
      thesis: o.active ? t("sc.oh.active", { v: f2(o.value), t: f2(o.threshold) })
                       : t("sc.oh.thesis", { d: pos(o.distance), t: f2(o.threshold), vt: f2(s.threshold) }),
      flips: [t("sc.oh.flip1"), t("sc.oh.flip2")], weight: o.weight, rationale: t("sc.oh.rationale"),
    });
    out.push({
      id: "shock",
      thesis: s.active ? t("sc.shock.active", { v: f2(s.value), t: f2(s.threshold) })
                       : t("sc.shock.thesis", { d: pos(s.distance), t: f2(s.threshold) }),
      flips: [t("sc.shock.flip1")], weight: s.weight, rationale: t("sc.shock.rationale"),
    });
    out.push({
      id: "digestion",
      thesis: d.active ? t("sc.dig.active", { v: f2(d.value), t: f2(d.threshold) })
                       : t("sc.dig.thesis", { d: pos(d.distance), t: f2(d.threshold) }),
      flips: [t("sc.dig.flip1"), t("sc.dig.flip2")], weight: d.weight, rationale: t("sc.dig.rationale"),
    });
    return out;
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

  global.TCD = { num, fmt, pct, esc, loadJSON, setText, setHTML, table, renderBanner, regimeLabel, regimeBadge, buildScenarios, chartDefaults };
})(window);
