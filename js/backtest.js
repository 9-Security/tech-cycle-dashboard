(function () {
  const { fmt, pct, esc, loadJSON, setText, renderBanner, regimeBadge, chartDefaults } = window.TCD;

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
    document.getElementById("asof-line").innerHTML =
      "Lag-1 regime strategy · nested walk-forward · as of <strong>" + esc(status.as_of) +
      "</strong> · regime: <strong>" + esc(status.regime && status.regime.label) + "</strong>";

    // Posture
    const w = status.weights || {};
    document.getElementById("p-regime").innerHTML = regimeBadge(status.regime);
    const sg = status.signals || {};
    setText("p-regime-sub", "month-end " + status.panel_end + (sg.pe_agg ? " · P/E " + fmt(sg.pe_agg, 1) + "x" : ""));
    setText("p-weight", fmt(w.executed_weight, 2));
    setText("p-weight-sub", "held through " + (w.in_force_month || "—"));
    const prov = status.provisional;
    if (prov) {
      document.getElementById("p-prov").innerHTML = regimeBadge(prov.regime);
      setText("p-prov-sub", prov.month + " · data through " + prov.data_through +
        " · next-month weight " + fmt(prov.next_month_weight_if_month_ended_today, 2));
    } else {
      setText("p-prov", "—");
      setText("p-prov-sub", "no month in progress");
    }

    // Metrics (fractions -> %)
    setText("m-sharpe", fmt(m.sharpe));
    setText("m-sharpe-sub", "B&H " + fmt(m.bh_sharpe) + " · in-sample " + fmt(m.insample_sharpe));
    setText("m-mdd", pct(m.max_dd));
    setText("m-mdd-sub", "B&H " + pct(m.bh_max_dd));
    setText("m-cagr", pct(m.cagr, 2));
    setText("m-cagr-sub", "vol " + pct(m.ann_vol));
    setText("m-nav", fmt(m.final_nav, 2));
    setText("m-bh", "B&H " + fmt(m.bh_final_nav, 2));

    setText("footer",
      "Source: " + data.source + " · " + data.dates[0] + " → " + data.dates[data.dates.length - 1] +
      " · " + data.dates.length + " OOS months · engine " + (status.engine_version || "—") +
      (status.git_sha ? " @ " + status.git_sha : ""));

    // Regime legend + strip
    const legend = document.getElementById("regimeLegend");
    Object.entries(data.regime_labels).forEach(([k, label]) => {
      const el = document.createElement("span");
      el.innerHTML = '<i class="swatch" style="background:' + data.regime_colors[k] + '"></i>' + k + " " + esc(label);
      legend.appendChild(el);
    });
    const strip = document.getElementById("regimeStrip");
    data.regime_spans.forEach((s) => {
      const d = document.createElement("div");
      d.style.background = s.color;
      d.style.flex = String(monthsBetween(s.start, s.end) + 1);
      d.title = s.label + ": " + s.start + " → " + s.end;
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
          line("Walk-forward strategy (OOS)", data.strategy_nav, "#2f6f4e", { borderWidth: 2.2 }),
          line("Buy & hold", data.benchmark_nav, "#6b6560", { borderDash: [4, 3] }),
          line("In-sample tuned (hindsight)", data.insample_nav, "#c45c26", { borderDash: [2, 3], borderWidth: 1.2 }),
        ],
      },
      options: { ...opts, scales: { ...opts.scales, y: { ...opts.scales.y, type: "logarithmic", title: { display: true, text: "NAV (log)" } } } },
    });

    new Chart(document.getElementById("auxChart"), {
      type: "line",
      data: {
        labels: data.dates,
        datasets: [
          line("VIX (monthly mean)", data.vix, "#8b1e3f", { yAxisID: "y" }),
          line("Overheat score", data.overheat_score, "#c45c26", { yAxisID: "y1" }),
          line("Earnings momentum score", data.earn_score, "#b08900", { yAxisID: "y1", borderWidth: 1 }),
          line("Executed risk weight", data.risk_weight, "#2f6f4e", { yAxisID: "y2", stepped: true, borderWidth: 1.8 }),
        ],
      },
      options: {
        ...opts,
        scales: {
          x: opts.scales.x,
          y: { position: "left", title: { display: true, text: "VIX" }, ticks: opts.scales.y.ticks, grid: { color: "#eee8de" } },
          y1: { position: "right", title: { display: true, text: "Score (z)" }, ticks: opts.scales.y.ticks, grid: { drawOnChartArea: false } },
          y2: { display: false, min: 0, max: 2 },
        },
      },
    });

    const capex = data.capex_ratio_firm.map((v, i) => (data.capex_src[i] === "SEC" ? v : null));
    new Chart(document.getElementById("capexChart"), {
      type: "line",
      data: { labels: data.dates, datasets: [line("TTM Capex / revenue (chain-linked)", capex, "#1e3a5f", { fill: true, backgroundColor: "rgba(30,58,95,0.08)", spanGaps: false })] },
      options: { ...opts, scales: { ...opts.scales, y: { ...opts.scales.y, ticks: { ...opts.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" } } } },
    });

    if (data.pe_agg) {
      const pe = data.pe_agg.map((v, i) => (data.val_src && data.val_src[i] === "PE" ? v : null));
      new Chart(document.getElementById("peChart"), {
        type: "line",
        data: { labels: data.dates, datasets: [line("Aggregate trailing P/E", pe, "#c45c26", { fill: true, backgroundColor: "rgba(196,92,38,0.08)" })] },
        options: { ...opts, scales: { ...opts.scales, y: { ...opts.scales.y, title: { display: true, text: "P/E (x)" } } } },
      });
    }

    const preview = document.getElementById("scenarioPreview");
    (scenarios.scenarios || []).forEach((s) => {
      const el = document.createElement("article");
      el.className = "scenario-card " + s.id;
      const sw = s.suggested_defensive_posture && s.suggested_defensive_posture.risk_weight;
      el.innerHTML = "<h3>" + esc(s.id) + " <span class='muted small'>(" + esc(s.horizon) + ")</span></h3>" +
        "<p>" + esc(s.thesis) + "</p><p>Risk weight: <span class='weight'>" + fmt(sw, 2) + "</span></p>";
      preview.appendChild(el);
    });
    setText("home-disclaimer", scenarios.disclaimer || "Not investment advice.");
  }

  function monthsBetween(a, b) {
    const x = new Date(a), y = new Date(b);
    return (y.getUTCFullYear() - x.getUTCFullYear()) * 12 + (y.getUTCMonth() - x.getUTCMonth());
  }

  boot().catch((e) => setText("footer", "Failed to load: " + e));
})();
