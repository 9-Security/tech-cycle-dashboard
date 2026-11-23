(function () {
  const { fmt, pct, esc, loadJSON, setText, renderBanner, chartDefaults } = window.TCD;

  function table(id, headers, rows) {
    document.getElementById(id).innerHTML =
      "<thead><tr>" + headers.map((h) => "<th>" + esc(h) + "</th>").join("") + "</tr></thead><tbody>" +
      rows.map((r) => "<tr>" + r.map((c) => "<td>" + c + "</td>").join("") + "</tr>").join("") + "</tbody>";
  }
  const tag = (v) => {
    const cls = v.startsWith("skillful") ? "PASS" : v.startsWith("inconclusive") ? "WARN" : "FAIL";
    return '<span class="dq ' + cls + '" title="' + esc(v) + '">' + esc(v.split(":")[0]) + "</span>";
  };
  const signed = (x, d = 2) => (x == null ? "—" : (x >= 0 ? "+" : "") + fmt(x, d));

  async function boot() {
    const [r, health] = await Promise.all([loadJSON("data/risk.json"), loadJSON("data/health.json").catch(() => null)]);
    document.body.dataset.ready = "1";
    renderBanner(health);
    document.getElementById("asof-line").innerHTML = "Risk estimates · walk-forward, out-of-sample · as of <strong>" + esc(r.as_of) + "</strong>";

    const vf = r.vol_forecast, vcur = vf.current.provisional || vf.current.month_end;
    const t0 = r.targets[0], cur0 = t0.current.provisional || t0.current.month_end;
    const skill = t0.verdict.startsWith("skillful");

    document.getElementById("summary").innerHTML =
      "<strong>What this page can and cannot tell you.</strong> Next-month <em>volatility</em> is forecastable out-of-sample " +
      "(R² " + fmt(vf.oos_r2_vs_mean, 2) + " vs the historical mean). The probability of a large <em>drawdown event</em> is not: the walk-forward model " +
      (skill ? "beats" : "does <strong>not</strong> beat") + " the historical base rate (" + esc(t0.verdict) + "). " +
      "Large drawdowns since 2008 came in only two episodes, both starting from calm markets, so there is too little to learn from. " +
      (skill ? "" : "The headline probability below is therefore the base rate; the model value is shown for reference only.");

    const st = r.short_term;
    if (st) {
      const so = chartDefaults();
      const c = st.current;
      setText("s-var", pct(c.var95_1d_simple_ret, 1));
      setText("s-var-sub", "1-in-20 trading days a loss larger than this is expected · from close " + c.date + " · " + c.label);
      setText("s-vol1", pct(c.vol_1d_ann, 0));
      setText("s-vol1-sub", "≈ " + pct(c.vol_1d, 1) + " daily move (1 sd) · EWMA " + pct(c.ewma_vol_ann, 0));
      setText("s-vol5", pct(c.vol_5d, 1));
      setText("s-vol5-sub", "1 sd over 5 days · " + pct(c.vol_5d_ann, 0) + " annualized");
      new Chart(document.getElementById("varChart"), {
        data: {
          labels: st.chart.dates,
          datasets: [
            { type: "bar", label: "Next-day return", data: st.chart.next_day_return, backgroundColor: st.chart.next_day_return.map((v, i) => v != null && st.chart.var95[i] != null && v < -st.chart.var95[i] ? "#8b1e3f" : "rgba(107,101,96,0.45)"), barPercentage: 1, categoryPercentage: 1 },
            { type: "line", label: "−95% VaR (forecast at prior close)", data: st.chart.var95.map((v) => (v == null ? null : -v)), borderColor: "#1e3a5f", borderWidth: 1.4, pointRadius: 0 },
          ],
        },
        options: { ...so, scales: { ...so.scales, y: { ...so.scales.y, ticks: { ...so.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" } } } },
      });
      const ev = st.evaluation, live = ev.var95.find((x) => x.model === st.live_model);
      setText("varNote", "Last 3 years, out-of-sample. Red bars are breaches (loss beyond the VaR set the evening before). Live model " + st.live_model.replace(/_/g, " ") +
        " breached on " + pct(live.rate, 2) + " of days since 2000 (target 5%).");
      table("stVarTable", ["Horizon", "Model", "QLIKE", "Vol correlation", "Days"],
        ev.variance.map((v) => [v.horizon + "d", esc(v.label) + (v.model === st.live_model ? " <strong>(live)</strong>" : ""), fmt(v.qlike, 4), fmt(v.corr_vol, 3), v.n]));
      const L = st.settings.models;
      table("stDmTable", ["Horizon", "Comparison", "QLIKE improvement", "Diebold-Mariano t", "Reading"],
        ev.dm.map((d) => [d.horizon + "d", esc(L[d.baseline] + " → " + L[d.challenger]), signed(d.qlike_improvement, 4), signed(d.dm_t, 2),
          d.dm_t >= 2 ? '<span class="dq PASS">better</span>' : d.dm_t <= -2 ? '<span class="dq FAIL">worse</span>' : '<span class="dq WARN">no sig. difference</span>']));
      const pv = (p) => (p < 0.05 ? '<span class="dq FAIL">' : '<span class="dq PASS">') + fmt(p, 3) + "</span>";
      table("stBtTable", ["Model", "Breaches", "Rate", "Kupiec p (coverage)", "Christoffersen p (independence)", "Avg VaR"],
        ev.var95.map((v) => [esc(v.label) + (v.model === st.live_model ? " <strong>(live)</strong>" : ""), v.breaches + "/" + v.n, pct(v.rate, 2), pv(v.p_value), pv(v.christoffersen.p_value), pct(v.avg_var, 2)]));
      document.getElementById("epuNote").innerHTML = "<strong>News-based EPU test:</strong> " + esc(st.epu_verdict) +
        ". Robustness (" + esc(st.robustness.spec) + " specification): " + esc(st.robustness.epu_verdict) + ". p &lt; 0.05 in the backtest table means the test rejects correct VaR coverage or independence.";
    }

    setText("r-vol", pct(vcur.vol, 0));
    setText("r-vol-sub", "90% band " + pct(vcur.band90[0], 0) + "–" + pct(vcur.band90[1], 0) + " · current 21d " + pct(vcur.current_rv21, 0) + " · for month after " + vcur.date);
    setText("r-dd", pct(skill ? cur0.p : t0.current.base_rate, 0));
    setText("r-dd-sub", skill ? "model estimate · 90% " + pct(cur0.ci90[0], 0) + "–" + pct(cur0.ci90[1], 0) : "historical base rate (" + t0.current.fit_rows + " months, " + t0.current.fit_events + " event months)");
    setText("r-model", pct(cur0.p, 0));
    setText("r-model-sub", "90% " + pct(cur0.ci90[0], 0) + "–" + pct(cur0.ci90[1], 0) + " · " + cur0.date + " · not skillful out-of-sample");
    if (skill) setText("r-model-sub", "90% " + pct(cur0.ci90[0], 0) + "–" + pct(cur0.ci90[1], 0) + " · " + cur0.date);

    const opts = chartDefaults();
    new Chart(document.getElementById("volChart"), {
      type: "line",
      data: {
        labels: vf.series.dates,
        datasets: [
          { label: "Forecast (made at month-end t)", data: vf.series.forecast, borderColor: "#1e3a5f", borderWidth: 1.6, pointRadius: 0 },
          { label: "Realized next month", data: vf.series.realized, borderColor: "#8b1e3f", borderWidth: 1, pointRadius: 0 },
        ],
      },
      options: { ...opts, scales: { ...opts.scales, y: { ...opts.scales.y, type: "logarithmic", ticks: { ...opts.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" } } } },
    });
    setText("volNote", "OLS on log 21-day realized vol and log VIX, refit each January. Out-of-sample R² " + fmt(vf.oos_r2_vs_mean, 2) +
      " vs historical mean, " + signed(vf.oos_r2_vs_persistence) + " vs 'next month = this month'; correlation " + fmt(vf.corr_pred_realized, 2) +
      " over " + vf.window.replace("->", "→") + ". Volatility clustering makes risk size predictable — not the direction or timing of a crash.");

    const rows = [];
    r.targets.forEach((t) => {
      [["full", "Vol + earnings + momentum"], ["vol_only", "Vol only"]].forEach(([k, lbl]) => {
        const e = t.evaluation[k];
        rows.push([esc(t.horizon + "m, " + Math.round(t.cut * 100) + "%"), esc(lbl), e.events + "/" + e.n, fmt(e.brier, 3), fmt(e.brier_climatology, 3), signed(e.bss),
          "[" + signed(e.bss_ci90[0]) + ", " + signed(e.bss_ci90[1]) + "]", fmt(e.auc, 2), k === "full" ? tag(t.verdict) : ""]);
      });
    });
    table("skillTable", ["Target (DD worse than)", "Model", "Event months", "Brier", "Brier (base rate)", "BSS", "90% CI", "AUC", "Verdict"], rows);

    table("eraTable", ["Era", "Months", "Event months", "Episodes", "AUC", "BSS"],
      t0.era_evaluation.map((e) => [esc(e.era), e.n, e.events, e.episodes, fmt(e.auc, 2), signed(e.bss)]));

    const pick = document.getElementById("tgtPick");
    r.targets.forEach((t, i) => { const o = document.createElement("option"); o.value = i; o.textContent = t.label; pick.appendChild(o); });
    let pc = null, rc = null;
    function draw(i) {
      const t = r.targets[i], s = t.series;
      if (pc) pc.destroy();
      pc = new Chart(document.getElementById("probChart"), {
        data: {
          labels: s.dates,
          datasets: [
            { type: "bar", label: "Event happened (1 = yes)", data: s.y.map((v) => (v == null ? null : v)), backgroundColor: "rgba(139,30,63,0.18)", barPercentage: 1, categoryPercentage: 1 },
            { type: "line", label: "Model probability", data: s.p_model, borderColor: "#1e3a5f", borderWidth: 1.6, pointRadius: 0 },
            { type: "line", label: "Base rate (expanding)", data: s.p_clim, borderColor: "#6b6560", borderDash: [4, 3], borderWidth: 1.2, pointRadius: 0 },
          ],
        },
        options: { ...opts, scales: { ...opts.scales, y: { ...opts.scales.y, min: 0, max: 1, ticks: { ...opts.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" } } } },
      });
      const rel = t.evaluation.full.reliability.filter((b) => b.n > 0);
      if (rc) rc.destroy();
      rc = new Chart(document.getElementById("relChart"), {
        type: "scatter",
        data: {
          datasets: [
            { label: "Observed vs predicted", data: rel.map((b) => ({ x: b.mean_pred, y: b.observed, n: b.n })), backgroundColor: "#1e3a5f", pointRadius: rel.map((b) => 3 + Math.sqrt(b.n)) },
            { label: "Perfect calibration", type: "line", data: [{ x: 0, y: 0 }, { x: 1, y: 1 }], borderColor: "#6b6560", borderDash: [4, 3], pointRadius: 0 },
          ],
        },
        options: {
          ...opts,
          interaction: { mode: "nearest", intersect: true },
          scales: {
            x: { type: "linear", min: 0, max: 1, title: { display: true, text: "Mean predicted probability" }, ticks: { ...opts.scales.x.ticks, callback: (v) => (v * 100).toFixed(0) + "%" } },
            y: { min: 0, max: 1, title: { display: true, text: "Observed frequency" }, ticks: { ...opts.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" } },
          },
        },
      });
      table("relTable", ["Predicted bin", "Months", "Mean predicted", "Observed"],
        t.evaluation.full.reliability.map((b) => [esc(b.bin), b.n, pct(b.mean_pred, 1), pct(b.observed, 1)]));
      const c = t.current.provisional || t.current.month_end;
      table("drvTable", ["Feature", "Value", "Coefficient (per sd)", "Log-odds contribution"],
        Object.keys(c.features).map((f) => [esc(r.settings.features[f] || f), fmt(c.features[f], 3), signed(t.current.coef[f]), signed(c.contributions_logodds[f])]));
    }
    pick.addEventListener("change", () => draw(+pick.value));
    draw(0);

    setText("footer", esc(r.settings.model) + " · " + r.settings.refit + " · drawdowns from " + r.settings.drawdown_basis + " · engine " + (r.engine_version || "—"));
  }

  boot().catch((e) => setText("footer", "Failed to load: " + e));
})();
