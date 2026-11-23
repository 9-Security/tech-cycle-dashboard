(function () {
  const { fmt, pct, esc, loadJSON, setText, setHTML, renderBanner, chartDefaults } = window.TCD;
  const { t, cols, lang } = window.TCD_I18N;
  const zh = lang !== "en";
  const LIGHT_RANK = { red: 0, yellow: 1, green: 2 };
  const signedPct = (x, d = 1) => (x == null ? "—" : (x >= 0 ? "+" : "") + pct(x, d));
  const nameOf = (s) => (zh ? s.name_zh : s.name_en);
  const money = (x) => (x == null ? "—" : x >= 100 ? fmt(x, 0) : fmt(x, 1));
  const priceFmt = (x) => (x == null ? "—" : x >= 1000 ? Math.round(x).toLocaleString("en-US") : fmt(x, 2));

  function vrTag(b) {
    const ok = b.verified;
    const tip = b.oos_days ? t("st.vr.tip", { n: b.oos_days, d: b.oos_start, r: pct(b.breach_rate, 2), k: fmt(b.kupiec_p, 2),
      c: fmt(b.christoffersen_p, 2), dm: (b.dm_t_vs_ewma >= 0 ? "+" : "") + fmt(b.dm_t_vs_ewma, 1) }) : "";
    return '<span class="dq ' + (ok ? "PASS" : "WARN") + '" title="' + esc(tip) + '">' + esc(t("st.vr." + b.reason)) + "</span>";
  }
  const dot = (lv) => '<span class="mini-dot ' + lv + '" title="' + esc(t("light.short." + lv)) + '"></span>' + esc(t("light.short." + lv));

  let DATA = null, selected = null, charts = [];

  function sorted(list, how) {
    const a = list.slice();
    const key = { light: (s) => LIGHT_RANK[s.level] * 10 - s.vol_percentile, vol: (s) => -s.vol_1d_ann,
      ret1m: (s) => s.ret_1m, dd: (s) => s.from_52w_high }[how];
    return key ? a.sort((x, y) => key(x) - key(y)) : a;
  }

  function renderTables() {
    const how = document.getElementById("sortPick").value;
    const common = cols("st.cols.common"), fund = cols("st.cols.fund");
    const row = (s) => {
      const base = [
        "<strong>" + esc(nameOf(s)) + "</strong> <span class='muted small'>" + esc(s.symbol) + "</span>",
        esc(t("seg." + s.segment)), dot(s.level), priceFmt(s.last_close), signedPct(s.ret_1m), signedPct(s.from_52w_high),
        pct(s.vol_1d_ann, 0), pct(s.var95, 1), vrTag(s.backtest), fmt(s.beta_1y, 2)];
      if (s.market !== "US") return base;
      const f = s.fundamentals || {};
      const g = (x) => (x == null ? esc(t("st.nm")) : signedPct(x, 0));
      return base.concat([f.pe == null ? esc(t("st.nm")) : fmt(f.pe, 1), g(f.revenue_growth), g(f.net_income_growth),
        f.capex_to_revenue == null ? "—" : pct(f.capex_to_revenue, 0), esc(f.last_filing || "—")]);
    };
    const draw = (id, market, headers) => {
      const list = sorted(DATA.stocks.filter((s) => s.market === market), how);
      const el = document.getElementById(id);
      el.innerHTML = "<thead><tr>" + headers.map((h) => "<th>" + esc(h) + "</th>").join("") + "</tr></thead><tbody>" +
        list.map((s) => '<tr tabindex="0" data-sym="' + esc(s.symbol) + '"' + (selected === s.symbol ? ' class="sel"' : "") + ">" +
          row(s).map((c) => "<td>" + c + "</td>").join("") + "</tr>").join("") + "</tbody>";
      el.querySelectorAll("tbody tr").forEach((tr) => {
        const go = () => showDetail(tr.dataset.sym, true);
        tr.addEventListener("click", go);
        tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
      });
    };
    draw("usTable", "US", common.concat(fund));
    draw("twTable", "TW", common);
  }

  function showDetail(sym, scroll) {
    const s = DATA.stocks.find((x) => x.symbol === sym);
    if (!s) return;
    selected = sym;
    document.querySelectorAll(".stock-table tbody tr").forEach((tr) => tr.classList.toggle("sel", tr.dataset.sym === sym));
    const box = document.getElementById("detail");
    box.hidden = false;
    box.dataset.level = s.level;
    setText("d-title", t("st.d.title", { name: nameOf(s), sym: s.symbol, seg: t("seg." + s.segment) }));
    setText("d-light", t("st.d.light." + s.level));
    const pts = [];
    pts.push(t("st.d.vol", { r: fmt(s.vol_ratio, 1), p: pct(s.vol_percentile, 0), y: (s.hist_start || "").slice(0, 4), m: pct(s.daily_move, 1) }));
    pts.push(t("st.d.var", { v: pct(s.var95, 1) }) + (s.backtest.verified ? "" : (zh ? "" : " ") + t("st.d.var.unverified", { why: t("st.vr." + s.backtest.reason) })));
    pts.push(t("st.d.mkt", { c: priceFmt(s.last_close), d: s.last_date, r1: signedPct(s.ret_1m), dd: signedPct(s.from_52w_high),
      b: fmt(s.beta_1y, 2), bench: DATA.benchmarks[s.market] }));
    const f = s.fundamentals;
    if (f) {
      const g = (x) => (x == null ? t("st.nm") : signedPct(x, 0));
      pts.push(t("st.d.fund", { f: f.last_filing || "—", rev: money(f.ttm_revenue_bn), ni: money(f.ttm_net_income_bn),
        rev_yi: f.ttm_revenue_bn == null ? "—" : Math.round(f.ttm_revenue_bn * 10).toLocaleString("en-US"),
        ni_yi: f.ttm_net_income_bn == null ? "—" : Math.round(f.ttm_net_income_bn * 10).toLocaleString("en-US"),
        rg: g(f.revenue_growth), ng: g(f.net_income_growth), pe: f.pe == null ? t("st.nm") : fmt(f.pe, 1),
        cx: f.capex_to_revenue == null ? "—" : pct(f.capex_to_revenue, 0) }));
    }
    document.getElementById("d-points").innerHTML = pts.map((x) => "<li>" + esc(x) + "</li>").join("");

    charts.forEach((c) => c.destroy());
    const o = chartDefaults(), ch = s.chart;
    charts = [
      new Chart(document.getElementById("d-price"), {
        type: "line",
        data: { labels: ch.dates, datasets: [{ label: t("st.d.price"), data: ch.close, borderColor: "#1e3a5f", borderWidth: 1.6, pointRadius: 0 }] },
        options: o,
      }),
      new Chart(document.getElementById("d-ret"), {
        data: {
          labels: ch.dates,
          datasets: [
            { type: "bar", label: t("st.d.ret"), data: ch.ret, barPercentage: 1, categoryPercentage: 1,
              backgroundColor: ch.ret.map((v, i) => (ch.var95[i] != null && v < -ch.var95[i] ? "#8b1e3f" : "rgba(107,101,96,0.45)")) },
            { type: "line", label: t("st.d.varline"), data: ch.var95.map((v) => (v == null ? null : -v)), borderColor: "#1e3a5f", borderWidth: 1.2, pointRadius: 0 },
          ],
        },
        options: { ...o, scales: { ...o.scales, y: { ...o.scales.y, ticks: { ...o.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" } } } },
      }),
    ];
    if (scroll) box.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function boot() {
    const [d, health] = await Promise.all([loadJSON("data/stocks.json"), loadJSON("data/health.json").catch(() => null)]);
    DATA = d;
    document.body.dataset.ready = "1";
    renderBanner(health);
    setHTML("asof-line", t("st.asof", { asof: esc(d.as_of) }));
    document.getElementById("sortPick").addEventListener("change", renderTables);
    renderTables();
    if (d.stocks.length) showDetail(d.stocks[0].symbol, false);
    setText("footer", t("st.footer", { ver: d.engine_version || "—" }));
  }

  boot().catch((e) => setText("footer", t("common.failed", { err: e })));
})();
