(function () {
  const fmt = (x, d = 2) =>
    x == null || Number.isNaN(Number(x)) ? "—" : Number(x).toFixed(d);
  const pct = (x) =>
    x == null || Number.isNaN(Number(x)) ? "—" : Number(x).toFixed(2) + "%";

  async function loadJSON(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(path + " → " + res.status);
    return res.json();
  }

  function commonOpts() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
      scales: {
        x: {
          ticks: { maxTicksLimit: 10, color: "#6b6560", font: { size: 10 } },
          grid: { color: "#eee8de" },
        },
        y: {
          ticks: { color: "#6b6560", font: { size: 10 } },
          grid: { color: "#eee8de" },
        },
      },
    };
  }

  async function boot() {
    const [data, status, scenarios] = await Promise.all([
      loadJSON("data/series.json"),
      loadJSON("data/status.json"),
      loadJSON("data/scenarios.json"),
    ]);

    document.body.dataset.ready = "1";

    const asOf = status.as_of || data.as_of || "—";
    const regimeLabel =
      (status.regime && status.regime.label) ||
      (data.regime_labels && data.regime_labels[String(data.regime.slice(-1)[0])]) ||
      "—";

    document.getElementById("asof-line").innerHTML =
      "Lag-1 regime strategy · tuned baseline · read-only analysis view · as of <strong>" +
      asOf +
      "</strong> · live regime: <strong>" +
      regimeLabel +
      "</strong>";

    document.getElementById("m-sharpe").textContent = fmt(data.metrics.sharpe);
    document.getElementById("m-mdd").textContent = pct(data.metrics.max_dd);
    document.getElementById("m-cagr").textContent = pct(data.metrics.cagr);
    document.getElementById("m-nav").textContent = fmt(data.metrics.final_nav, 3);
    document.getElementById("m-bh").textContent =
      "BH " + fmt(data.metrics.bh_final_nav, 3);

    document.getElementById("footer").textContent =
      "Snapshot source: " +
      data.source +
      " · " +
      data.dates[0] +
      " → " +
      data.dates[data.dates.length - 1] +
      " · " +
      data.dates.length +
      " months · " +
      (data.snapshot_label || "baked snapshot");

    const legend = document.getElementById("regimeLegend");
    Object.entries(data.regime_labels).forEach(function ([k, label]) {
      const el = document.createElement("span");
      el.innerHTML =
        '<i class="swatch" style="background:' +
        data.regime_colors[k] +
        '"></i>' +
        k +
        " " +
        label;
      legend.appendChild(el);
    });

    const strip = document.getElementById("regimeStrip");
    const totalMs =
      new Date(data.dates[data.dates.length - 1]) - new Date(data.dates[0]) || 1;
    data.regime_spans.forEach(function (s) {
      const d = document.createElement("div");
      d.style.background = s.color;
      d.style.flex = String(
        Math.max(0.2, ((new Date(s.end) - new Date(s.start)) / totalMs) * 100)
      );
      d.title = s.label + ": " + s.start + " → " + s.end;
      strip.appendChild(d);
    });

    const opts = commonOpts();

    new Chart(document.getElementById("navChart"), {
      type: "line",
      data: {
        labels: data.dates,
        datasets: [
          {
            label: "Regime strategy NAV",
            data: data.strategy_nav,
            borderColor: "#2f6f4e",
            backgroundColor: "rgba(47,111,78,0.08)",
            borderWidth: 2,
            pointRadius: 0,
            fill: true,
            tension: 0.05,
          },
          {
            label: "Buy & hold NAV",
            data: data.benchmark_nav,
            borderColor: "#6b6560",
            borderWidth: 1.5,
            borderDash: [4, 3],
            pointRadius: 0,
            fill: false,
            tension: 0.05,
          },
        ],
      },
      options: {
        ...opts,
        scales: {
          ...opts.scales,
          y: {
            ...opts.scales.y,
            title: { display: true, text: "NAV (start≈1)" },
            type: "logarithmic",
          },
        },
      },
    });

    new Chart(document.getElementById("regimeChart"), {
      type: "line",
      data: {
        labels: data.dates,
        datasets: [
          {
            label: "Regime (1 OH · 2 Shock · 3 Digestion · 4 Normal)",
            data: data.regime,
            borderColor: "#1c1917",
            borderWidth: 1.25,
            pointRadius: 0,
            stepped: true,
            fill: false,
          },
        ],
      },
      options: {
        ...opts,
        scales: {
          ...opts.scales,
          y: {
            min: 0.5,
            max: 4.5,
            ticks: {
              stepSize: 1,
              callback: function (v) {
                return data.regime_labels[v] || v;
              },
              color: "#6b6560",
              font: { size: 10 },
            },
            grid: { color: "#eee8de" },
          },
        },
      },
    });

    const auxDatasets = [];
    if (data.vix) {
      auxDatasets.push({
        label: "VIX",
        data: data.vix,
        borderColor: "#8b1e3f",
        borderWidth: 1.5,
        pointRadius: 0,
        yAxisID: "y",
        tension: 0.05,
      });
    }
    if (data.overheat_score) {
      auxDatasets.push({
        label: "Overheat score",
        data: data.overheat_score,
        borderColor: "#c45c26",
        borderWidth: 1.5,
        pointRadius: 0,
        yAxisID: "y1",
        tension: 0.05,
      });
    }
    if (data.risk_weight) {
      auxDatasets.push({
        label: "Executed risk weight",
        data: data.risk_weight,
        borderColor: "#2f6f4e",
        borderWidth: 1.75,
        pointRadius: 0,
        yAxisID: "y1",
        stepped: true,
      });
    }

    new Chart(document.getElementById("auxChart"), {
      type: "line",
      data: { labels: data.dates, datasets: auxDatasets },
      options: {
        ...opts,
        scales: {
          x: opts.scales.x,
          y: {
            position: "left",
            title: { display: true, text: "VIX" },
            ticks: { color: "#6b6560", font: { size: 10 } },
            grid: { color: "#eee8de" },
          },
          y1: {
            position: "right",
            title: { display: true, text: "Score / weight" },
            min: -2,
            max: 1.2,
            ticks: { color: "#6b6560", font: { size: 10 } },
            grid: { drawOnChartArea: false },
          },
        },
      },
    });

    // Home scenarios preview
    const preview = document.getElementById("scenarioPreview");
    (scenarios.scenarios || []).forEach(function (s) {
      const el = document.createElement("article");
      el.className = "scenario-card " + s.id;
      const w =
        s.suggested_defensive_posture && s.suggested_defensive_posture.risk_weight;
      el.innerHTML =
        "<h3>" +
        s.id +
        " <span style='font-weight:500;color:#6b6560;font-size:0.8rem'>(" +
        (s.horizon || "") +
        ")</span></h3>" +
        "<p>" +
        (s.thesis || "") +
        "</p>" +
        "<p>Suggested weight: <span class='weight'>" +
        fmt(w, 4) +
        "</span></p>";
      preview.appendChild(el);
    });

    document.getElementById("home-disclaimer").textContent =
      scenarios.disclaimer ||
      "Scenario analysis for risk discussion only. Not investment advice. Not an auto-trading signal.";
  }

  boot().catch(function (e) {
    document.getElementById("footer").textContent = "Failed to load: " + e;
  });
})();
