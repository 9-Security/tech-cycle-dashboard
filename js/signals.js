(function () {
  const { fmt, pct, esc, loadJSON, setText, setHTML, table, renderBanner, chartDefaults } = window.TCD;
  const { t, has, cols } = window.TCD_I18N;

  const sigName = (b) => (has("sig.name." + b.signal) ? t("sig.name." + b.signal) : b.label);
  const kindOf = (v) => (v.startsWith("supports") ? "supports" : v.startsWith("contradicts") ? "contradicts" : "inconclusive");

  // Full localized reading, e.g. "contradicts de-risking: high signal preceded HIGHER returns".
  function reading(v, kind, side) {
    const k = kindOf(v);
    if (k === "inconclusive") return t("sig.v.inconclusive");
    const sep = window.TCD_I18N.lang === "en" ? ": " : "：";
    return t("sig.v.prefix." + k) + sep + t("sig.v." + kind + "." + k, { side: t("side." + side) });
  }
  function verdictTag(v, kind, side) {
    const k = kindOf(v);
    const cls = k === "supports" ? "PASS" : k === "contradicts" ? "FAIL" : "WARN";
    return '<span class="dq ' + cls + '" title="' + esc(reading(v, kind, side)) + '">' + esc(t("tag." + k)) + "</span>";
  }
  const sgn = (x) => (x >= 0 ? "+" : "");
  const pv = (p) => (p == null ? "—" : (p < 0.05 ? "<strong>" + fmt(p, 3) + "</strong>" : fmt(p, 2)));

  async function boot() {
    const [d, health] = await Promise.all([loadJSON("data/signals.json"), loadJSON("data/health.json").catch(() => null)]);
    document.body.dataset.ready = "1";
    renderBanner(health);
    setHTML("asof-line", t("sig.asof", { asof: esc(d.as_of) }));

    const w = d.window, u = d.unconditional;
    const oh = d.buckets.find((b) => b.signal === "overheat_score");
    setHTML("summary", t("sig.summary", { a: esc(w.start), b: esc(w.last_month_with_12m_forward), r: pct(u.fwd12_mean),
      cut: pct(d.settings.drawdown_cut, 0), p: pct(u.p_dd_below, 0),
      rv: esc(reading(oh.return_verdict, "ret", oh.derisk_side)), dv: esc(reading(oh.risk_verdict, "risk", oh.derisk_side)) }));

    table("verdictTable", cols("sig.verdict.cols"), d.buckets.map((b) => [esc(sigName(b)), esc(t("side." + b.derisk_side)),
      sgn(b.spread_top_minus_bottom) + fmt(b.spread_top_minus_bottom * 100, 1), pv(b.spread_p), verdictTag(b.return_verdict, "ret", b.derisk_side),
      sgn(b.dd_prob_spread) + fmt(b.dd_prob_spread * 100, 0), pv(b.dd_prob_spread_p), verdictTag(b.risk_verdict, "risk", b.derisk_side)]));

    const pick = document.getElementById("sigPick");
    d.buckets.forEach((b) => {
      const o = document.createElement("option");
      o.value = b.signal; o.textContent = sigName(b);
      pick.appendChild(o);
    });
    const opts = chartDefaults();
    let chart = null;
    function drawBuckets(sig) {
      const b = d.buckets.find((x) => x.signal === sig);
      const labels = b.buckets.map((q) => "Q" + q.bucket + (q.bucket === 1 ? t("sig.q.low") : q.bucket === 5 ? t("sig.q.high") : "") + " n=" + q.n);
      if (chart) chart.destroy();
      chart = new Chart(document.getElementById("bucketChart"), {
        data: {
          labels,
          datasets: [
            { type: "bar", label: t("sig.q.ret"), data: b.buckets.map((q) => q.fwd12_mean), backgroundColor: "rgba(47,111,78,0.65)", yAxisID: "y" },
            { type: "line", label: t("sig.q.dd", { cut: pct(d.settings.drawdown_cut, 0) }), data: b.buckets.map((q) => q.p_dd_below), borderColor: "#8b1e3f", backgroundColor: "#8b1e3f", pointRadius: 4, yAxisID: "y1" },
          ],
        },
        options: {
          ...opts,
          scales: {
            x: { ticks: opts.scales.x.ticks, grid: { display: false } },
            y: { position: "left", title: { display: true, text: t("sig.q.ret.axis") }, ticks: { ...opts.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" }, grid: { color: "#eee8de" } },
            y1: { position: "right", min: 0, max: 1, title: { display: true, text: t("sig.q.dd.axis") }, ticks: { ...opts.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" }, grid: { drawOnChartArea: false } },
          },
        },
      });
    }
    pick.addEventListener("change", () => drawBuckets(pick.value));
    drawBuckets("overheat_score");

    const sc = d.scatter, early = [], late = [];
    sc.dates.forEach((dt, i) => (dt < "2013-01-01" ? early : late).push({ x: sc.overheat_score[i], y: sc.fwd12[i], d: dt }));
    new Chart(document.getElementById("scatterChart"), {
      type: "scatter",
      data: {
        datasets: [
          { label: t("sig.sc.early"), data: early, backgroundColor: "rgba(107,101,96,0.55)", pointRadius: 2.5 },
          { label: t("sig.sc.late"), data: late, backgroundColor: "rgba(196,92,38,0.75)", pointRadius: 2.5 },
        ],
      },
      options: {
        ...opts,
        interaction: { mode: "nearest", intersect: true },
        plugins: { ...opts.plugins, tooltip: { callbacks: { label: (c) => t("sig.sc.tip", { d: c.raw.d, x: fmt(c.raw.x), y: pct(c.raw.y) }) } } },
        scales: {
          x: { type: "linear", title: { display: true, text: t("sig.sc.x") }, ticks: opts.scales.x.ticks, grid: { color: "#eee8de" } },
          y: { title: { display: true, text: t("sig.sc.y") }, ticks: { ...opts.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" }, grid: { color: "#eee8de" } },
        },
      },
    });

    const hz = d.settings.horizons;
    const sigs = [...new Set(d.ic.map((r) => r.signal))];
    table("icTable", [t("sig.ic.col0")].concat(hz.map((h) => t("sig.ic.col", { h: h }))), sigs.map((sig) => {
      const rows = d.ic.filter((r) => r.signal === sig);
      return [esc(has("sig.name." + sig) ? t("sig.name." + sig) : rows[0].label)].concat(hz.map((h) => {
        const r = rows.find((x) => x.horizon === h);
        const tv = r.t != null ? r.t : r.nw_t;
        const strong = Math.abs(tv) >= 2;
        return (strong ? "<strong>" : "") + sgn(r.ic) + fmt(r.ic) + " (" + fmt(tv, 1) + ")" + (strong ? "</strong>" : "");
      }));
    }));

    const eras = [...new Set(d.eras.map((e) => e.era))];
    table("eraTable", [t("sig.ic.col0")].concat(eras.map((e) => t("sig.era.col", { era: has("era." + e) ? t("era." + e) : e }))),
      [...new Set(d.eras.map((e) => e.signal))].map((sig) => [esc(has("sig.name." + sig) ? t("sig.name." + sig) : sig)].concat(eras.map((era) => {
        const e = d.eras.find((x) => x.signal === sig && x.era === era);
        return sgn(e.ic_12m) + fmt(e.ic_12m) + " (" + fmt(e.t_12m != null ? e.t_12m : e.nw_t_12m, 1) + ")";
      }))));

    table("thrTable", cols("sig.thr.cols"), d.thresholds.map((x) => [fmt(x.threshold, 1), x.months_above, pct(x.share_above, 0),
      pct(x.fwd12_above), pct(x.fwd12_below), pct(x.p_dd_above, 0), pct(x.p_dd_below, 0)]));

    setText("footer", t("sig.footer", { n: d.settings.bucket_min_history, ver: d.engine_version || "—" }));
  }

  boot().catch((e) => setText("footer", t("common.failed", { err: e })));
})();
