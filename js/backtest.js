(function () {
  const { fmt, pct, esc, loadJSON, setText, setHTML, renderBanner, regimeLabel, regimeBadge, buildScenarios, chartDefaults } = window.TCD;
  const { t } = window.TCD_I18N;

  async function boot() {
    const [data, status, scenarios, health] = await Promise.all([
      loadJSON("data/series.json"),
      loadJSON("data/status.json"),
      loadJSON("data/scenarios.json"),
      loadJSON("data/health.json").catch(() => null),
    ]);
    document.body.dataset.ready = "1";
    renderBanner(health);

    const m = data.metrics || {};
    setHTML("asof-line", t("index.asof", { asof: esc(status.as_of), regime: esc(regimeLabel(status.regime && status.regime.code, status.regime && status.regime.label)) }));

    // Posture
    const w = status.weights || {};
    setHTML("p-regime", regimeBadge(status.regime));
    const sg = status.signals || {};
    setText("p-regime-sub", t("index.sub.monthEnd", { date: status.panel_end }) + (sg.pe_agg ? t("index.sub.pe", { pe: fmt(sg.pe_agg, 1) }) : ""));
    setText("p-weight", fmt(w.executed_weight, 2));
    setText("p-weight-sub", t("index.sub.heldThrough", { m: w.in_force_month || "—" }));
    const prov = status.provisional;
    if (prov) {
      setHTML("p-prov", regimeBadge(prov.regime));
      setText("p-prov-sub", t("index.sub.prov", { m: prov.month, d: prov.data_through, w: fmt(prov.next_month_weight_if_month_ended_today, 2) }));
    } else {
      setText("p-prov", "—");
      setText("p-prov-sub", t("index.sub.noProv"));
    }

    const c3 = status.candidate;
    if (c3) {
      setText("p-v3", fmt(c3.executed_weight, 2));
      const me = c3.month_end, pv = c3.provisional;
      setText("p-v3-sub", t("index.sub.v3", { state: t("state." + me.state.code), vol: pct(me.vol_forecast, 0), scale: fmt(me.vol_scale, 2),
        tilt: (me.tilt >= 0 ? "+" : "") + fmt(me.tilt, 2) }) + (pv ? t("index.sub.v3mtd", { w: fmt(pv.weight, 2) }) : ""));
    }

    const rk = status.risk;
    if (rk) {
      const vf = rk.vol_forecast_next_month;
      setText("p-vol", pct(vf.vol, 0));
      let sub = t("index.sub.vol", { lo: pct(vf.band90[0], 0), hi: pct(vf.band90[1], 0) });
      sub += rk.headline_source === "model" ? t("index.sub.volModel", { p: pct(rk.headline_p, 0) }) : t("index.sub.volBase", { p: pct(rk.base_rate, 0) });
      if (rk.short_term) sub += t("index.sub.var", { v: pct(rk.short_term.var95_1d_simple_ret, 1) });
      setHTML("p-vol-sub", sub + t("index.sub.riskLink"));
    }

    // Metrics (fractions -> %)
    setText("m-sharpe", fmt(m.sharpe));
    setText("m-sharpe-sub", t("index.m.sharpeSub", { bh: fmt(m.bh_sharpe), is: fmt(m.insample_sharpe) }));
    setText("m-mdd", pct(m.max_dd));
    setText("m-mdd-sub", t("index.m.bh", { v: pct(m.bh_max_dd) }));
    setText("m-cagr", pct(m.cagr, 2));
    setText("m-cagr-sub", t("index.m.vol", { v: pct(m.ann_vol) }));
    setText("m-nav", fmt(m.final_nav, 2));
    setText("m-bh", t("index.m.bh", { v: fmt(m.bh_final_nav, 2) }));

    setText("footer", t("index.footer", { src: data.source, from: data.dates[0], to: data.dates[data.dates.length - 1],
      n: data.dates.length, ver: (status.engine_version || "—") + (status.git_sha ? " @ " + status.git_sha : "") }));

    // Regime legend + strip
    const legend = document.getElementById("regimeLegend");
    Object.keys(data.regime_labels).forEach((k) => {
      const el = document.createElement("span");
      el.innerHTML = '<i class="swatch" style="background:' + data.regime_colors[k] + '"></i>' + k + " " + esc(regimeLabel(k, data.regime_labels[k]));
      legend.appendChild(el);
    });
    const strip = document.getElementById("regimeStrip");
    data.regime_spans.forEach((s) => {
      const d = document.createElement("div");
      d.style.background = s.color;
      d.style.flex = String(monthsBetween(s.start, s.end) + 1);
      d.title = regimeLabel(s.regime, s.label) + ": " + s.start + " → " + s.end;
      strip.appendChild(d);
    });

    const opts = chartDefaults();
    const line = (label, values, color, extra) =>
      Object.assign({ label, data: values, borderColor: color, borderWidth: 1.5, pointRadius: 0, tension: 0.05, fill: false }, extra || {});

    new Chart(document.getElementById("navChart"), {
      type: "line",
      data: {
        labels: data.dates,
        datasets: [
          line(t("index.nav.v2"), data.strategy_nav, "#2f6f4e", { borderWidth: 2.2 }),
          line(t("index.nav.bh"), data.benchmark_nav, "#6b6560", { borderDash: [4, 3] }),
          line(t("index.nav.is"), data.insample_nav, "#c45c26", { borderDash: [2, 3], borderWidth: 1.2 }),
        ].concat(data.candidate ? [line(t("index.nav.v3"), data.candidate.strategy_nav, "#1e3a5f", { borderWidth: 1.8 })] : []),
      },
      options: { ...opts, scales: { ...opts.scales, y: { ...opts.scales.y, type: "logarithmic", title: { display: true, text: t("index.nav.axis") } } } },
    });

    new Chart(document.getElementById("auxChart"), {
      type: "line",
      data: {
        labels: data.dates,
        datasets: [
          line(t("index.aux.vix"), data.vix, "#8b1e3f", { yAxisID: "y" }),
          line(t("index.aux.oh"), data.overheat_score, "#c45c26", { yAxisID: "y1" }),
          line(t("index.aux.earn"), data.earn_score, "#b08900", { yAxisID: "y1", borderWidth: 1 }),
          line(t("index.aux.w"), data.risk_weight, "#2f6f4e", { yAxisID: "y2", stepped: true, borderWidth: 1.8 }),
        ],
      },
      options: {
        ...opts,
        scales: {
          x: opts.scales.x,
          y: { position: "left", title: { display: true, text: "VIX" }, ticks: opts.scales.y.ticks, grid: { color: "#eee8de" } },
          y1: { position: "right", title: { display: true, text: t("index.aux.score") }, ticks: opts.scales.y.ticks, grid: { drawOnChartArea: false } },
          y2: { display: false, min: 0, max: 2 },
        },
      },
    });

    const capex = data.capex_ratio_firm.map((v, i) => (data.capex_src[i] === "SEC" ? v : null));
    new Chart(document.getElementById("capexChart"), {
      type: "line",
      data: { labels: data.dates, datasets: [line(t("index.capex.series"), capex, "#1e3a5f", { fill: true, backgroundColor: "rgba(30,58,95,0.08)", spanGaps: false })] },
      options: { ...opts, scales: { ...opts.scales, y: { ...opts.scales.y, ticks: { ...opts.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" } } } },
    });

    if (data.pe_agg) {
      const pe = data.pe_agg.map((v, i) => (data.val_src && data.val_src[i] === "PE" ? v : null));
      new Chart(document.getElementById("peChart"), {
        type: "line",
        data: { labels: data.dates, datasets: [line(t("index.pe.series"), pe, "#c45c26", { fill: true, backgroundColor: "rgba(196,92,38,0.08)" })] },
        options: { ...opts, scales: { ...opts.scales, y: { ...opts.scales.y, title: { display: true, text: t("index.pe.axis") } } } },
      });
    }

    const preview = document.getElementById("scenarioPreview");
    buildScenarios(status, scenarios).forEach((s) => {
      const el = document.createElement("article");
      el.className = "scenario-card " + s.id;
      el.innerHTML = "<h3>" + esc(t("sc.id." + s.id)) + " <span class='muted small'>(" + esc(t("sc.horizon")) + ")</span></h3>" +
        "<p>" + esc(s.thesis) + "</p><p>" + esc(t("index.sc.weight")) + " <span class='weight'>" + fmt(s.weight, 2) + "</span></p>";
      preview.appendChild(el);
    });
  }

  function monthsBetween(a, b) {
    const x = new Date(a), y = new Date(b);
    return (y.getUTCFullYear() - x.getUTCFullYear()) * 12 + (y.getUTCMonth() - x.getUTCMonth());
  }

  boot().catch((e) => setText("footer", t("common.failed", { err: e })));
})();
