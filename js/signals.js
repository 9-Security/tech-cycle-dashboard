(function () {
  const { fmt, pct, esc, loadJSON, setText, renderBanner, chartDefaults } = window.TCD;

  function table(id, headers, rows) {
    document.getElementById(id).innerHTML =
      "<thead><tr>" + headers.map((h) => "<th>" + esc(h) + "</th>").join("") + "</tr></thead><tbody>" +
      rows.map((r) => "<tr>" + r.map((c) => "<td>" + c + "</td>").join("") + "</tr>").join("") + "</tbody>";
  }

  function verdictTag(v) {
    const cls = v.startsWith("supports") ? "PASS" : v.startsWith("contradicts") ? "FAIL" : "WARN";
    const short = v.startsWith("supports") ? "supports" : v.startsWith("contradicts") ? "contradicts" : "inconclusive";
    return '<span class="dq ' + cls + '" title="' + esc(v) + '">' + short + "</span>";
  }

  const ci = (a) => "[" + (a[0] >= 0 ? "+" : "") + fmt(a[0] * 100, 1) + ", " + (a[1] >= 0 ? "+" : "") + fmt(a[1] * 100, 1) + "]";

  async function boot() {
    const [d, health] = await Promise.all([loadJSON("data/signals.json"), loadJSON("data/health.json").catch(() => null)]);
    document.body.dataset.ready = "1";
    renderBanner(health);
    document.getElementById("asof-line").innerHTML = "Stand-alone signal tests · as of <strong>" + esc(d.as_of) + "</strong>";

    const w = d.window, u = d.unconditional;
    const oh = d.buckets.find((b) => b.signal === "overheat_score");
    document.getElementById("summary").innerHTML =
      "Each signal is tested on its own, outside the regime rules: does a high (or low) reading precede weaker returns or more frequent " +
      "large drawdowns of the risk asset? Window " + esc(w.start) + " → " + esc(w.last_month_with_12m_forward) +
      " (12-month targets). Unconditional: next-12m excess log return " + pct(u.fwd12_mean) +
      ", probability of a drawdown worse than " + pct(d.settings.drawdown_cut, 0) + " " + pct(u.p_dd_below, 0) + ".<br/><br/>" +
      "<strong>Overheat score:</strong> " + esc(oh.return_verdict) + "; " + esc(oh.risk_verdict) + ".";

    table("verdictTable",
      ["Signal", "De-risk side", "Return Q5−Q1 (pp)", "90% CI", "Returns", "P(DD) Q5−Q1 (pp)", "90% CI", "Drawdowns"],
      d.buckets.map((b) => [esc(b.signal), esc(b.derisk_side), (b.spread_top_minus_bottom >= 0 ? "+" : "") + fmt(b.spread_top_minus_bottom * 100, 1), ci(b.spread_ci90),
        verdictTag(b.return_verdict), (b.dd_prob_spread >= 0 ? "+" : "") + fmt(b.dd_prob_spread * 100, 0), ci(b.dd_prob_spread_ci90), verdictTag(b.risk_verdict)]));

    // Quintile chart with picker
    const pick = document.getElementById("sigPick");
    d.buckets.forEach((b) => {
      const o = document.createElement("option");
      o.value = b.signal; o.textContent = b.label;
      pick.appendChild(o);
    });
    const opts = chartDefaults();
    let chart = null;
    function drawBuckets(sig) {
      const b = d.buckets.find((x) => x.signal === sig);
      const labels = b.buckets.map((q) => "Q" + q.bucket + (q.bucket === 1 ? " (low)" : q.bucket === 5 ? " (high)" : "") + " n=" + q.n);
      if (chart) chart.destroy();
      chart = new Chart(document.getElementById("bucketChart"), {
        data: {
          labels,
          datasets: [
            { type: "bar", label: "Mean next-12m excess log return", data: b.buckets.map((q) => q.fwd12_mean), backgroundColor: "rgba(47,111,78,0.65)", yAxisID: "y" },
            { type: "line", label: "P(drawdown < " + pct(d.settings.drawdown_cut, 0) + ")", data: b.buckets.map((q) => q.p_dd_below), borderColor: "#8b1e3f", backgroundColor: "#8b1e3f", pointRadius: 4, yAxisID: "y1" },
          ],
        },
        options: {
          ...opts,
          scales: {
            x: { ticks: opts.scales.x.ticks, grid: { display: false } },
            y: { position: "left", title: { display: true, text: "Return" }, ticks: { ...opts.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" }, grid: { color: "#eee8de" } },
            y1: { position: "right", min: 0, max: 1, title: { display: true, text: "Drawdown probability" }, ticks: { ...opts.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" }, grid: { drawOnChartArea: false } },
          },
        },
      });
    }
    pick.addEventListener("change", () => drawBuckets(pick.value));
    drawBuckets("overheat_score");

    // Scatter split by era
    const sc = d.scatter, early = [], late = [];
    sc.dates.forEach((dt, i) => (dt < "2013-01-01" ? early : late).push({ x: sc.overheat_score[i], y: sc.fwd12[i], d: dt }));
    new Chart(document.getElementById("scatterChart"), {
      type: "scatter",
      data: {
        datasets: [
          { label: "1993–2012 (macro proxies)", data: early, backgroundColor: "rgba(107,101,96,0.55)", pointRadius: 2.5 },
          { label: "2013+ (SEC firm-level)", data: late, backgroundColor: "rgba(196,92,38,0.75)", pointRadius: 2.5 },
        ],
      },
      options: {
        ...opts,
        interaction: { mode: "nearest", intersect: true },
        plugins: { ...opts.plugins, tooltip: { callbacks: { label: (c) => c.raw.d + ": score " + fmt(c.raw.x) + ", next 12m " + pct(c.raw.y) } } },
        scales: {
          x: { type: "linear", title: { display: true, text: "Overheat score at month-end" }, ticks: opts.scales.x.ticks, grid: { color: "#eee8de" } },
          y: { title: { display: true, text: "Next-12m excess log return" }, ticks: { ...opts.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" }, grid: { color: "#eee8de" } },
        },
      },
    });

    const hz = d.settings.horizons;
    table("icTable", ["Signal"].concat(hz.map((h) => h + "m IC (t)")),
      Object.keys(Object.fromEntries(d.ic.map((r) => [r.signal, 1]))).map((sig) => {
        const rows = d.ic.filter((r) => r.signal === sig);
        return [esc(rows[0].label)].concat(hz.map((h) => {
          const r = rows.find((x) => x.horizon === h);
          const strong = Math.abs(r.nw_t) >= 2;
          return (strong ? "<strong>" : "") + (r.ic >= 0 ? "+" : "") + fmt(r.ic) + " (" + fmt(r.nw_t, 1) + ")" + (strong ? "</strong>" : "");
        }));
      }));

    const eras = [...new Set(d.eras.map((e) => e.era))];
    table("eraTable", ["Signal"].concat(eras.map((e) => e + " IC (t)")),
      [...new Set(d.eras.map((e) => e.signal))].map((sig) => [esc(sig)].concat(eras.map((era) => {
        const e = d.eras.find((x) => x.signal === sig && x.era === era);
        return (e.ic_12m >= 0 ? "+" : "") + fmt(e.ic_12m) + " (" + fmt(e.nw_t_12m, 1) + ")";
      }))));

    table("thrTable", ["Overheat >", "Months above", "Share", "Next-12m ret. above", "below", "P(dd) above", "below"],
      d.thresholds.map((t) => [fmt(t.threshold, 1), t.months_above, pct(t.share_above, 0), pct(t.fwd12_above), pct(t.fwd12_below), pct(t.p_dd_above, 0), pct(t.p_dd_below, 0)]));

    setText("footer", "Settings: " + d.settings.t_stat + " · " + d.settings.bootstrap + " · buckets need " + d.settings.bucket_min_history + " months of history · engine " + (d.engine_version || "—"));
  }

  boot().catch((e) => setText("footer", "Failed to load: " + e));
})();
