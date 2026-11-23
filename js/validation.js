(function () {
  const { fmt, pct, esc, loadJSON, setText, renderBanner } = window.TCD;

  function table(id, headers, rows) {
    const el = document.getElementById(id);
    el.innerHTML =
      "<thead><tr>" + headers.map((h) => "<th>" + esc(h) + "</th>").join("") + "</tr></thead><tbody>" +
      rows.map((r) => "<tr>" + r.map((c) => "<td>" + c + "</td>").join("") + "</tr>").join("") + "</tbody>";
  }

  function heatColor(v, lo, hi) {
    if (v == null) return "#eee";
    const t = hi > lo ? (v - lo) / (hi - lo) : 0.5;
    // muted red -> neutral -> green
    const r = Math.round(196 + (47 - 196) * t), g = Math.round(92 + (111 - 92) * t), b = Math.round(38 + (78 - 38) * t);
    return "rgba(" + r + "," + g + "," + b + ",0.55)";
  }

  async function boot() {
    const [v, health] = await Promise.all([loadJSON("data/validation.json"), loadJSON("data/health.json").catch(() => null)]);
    document.body.dataset.ready = "1";
    renderBanner(health);
    const s = v.summary;
    document.getElementById("asof-line").innerHTML = "Nested walk-forward · as of <strong>" + esc(v.as_of) + "</strong>";

    const oos = v.oos, bh = v.bh, isb = v.insample_best;
    const verdict = oos.sharpe >= bh.sharpe
      ? "The out-of-sample strategy matched or beat buy &amp; hold on Sharpe."
      : "The out-of-sample strategy <strong>under-performed</strong> buy &amp; hold on Sharpe (" + fmt(oos.sharpe) + " vs " + fmt(bh.sharpe) +
        "). The in-sample-tuned version looks far better (" + fmt(isb.full_sample.sharpe) + " full sample) — that gap is hindsight, not skill.";
    document.getElementById("summary").innerHTML =
      "<strong>Out-of-sample window:</strong> " + esc(s.oos_start) + " → " + esc(s.oos_end) + " (" + s.oos_months + " months). " +
      "<strong>Search space:</strong> " + s.grid_size + " configurations. <strong>Objective:</strong> " + esc(s.objective) + ". " +
      "<strong>Refit:</strong> " + esc(s.refit) + ", training from " + esc(s.train_start) + ".<br/><br/>" + verdict;

    const row = (label, m) => [esc(label), fmt(m.sharpe), pct(m.cagr, 2), pct(m.ann_vol), pct(m.max_dd), fmt(m.calmar), fmt(m.final_nav, 2), fmt(m.avg_weight, 2)];
    table("cmpTable", ["Track", "Sharpe", "CAGR", "Vol", "Max DD", "Calmar", "Final NAV", "Avg weight"], [
      row("Walk-forward strategy (OOS)", oos),
      row("In-sample best, same window (hindsight)", isb.on_oos_window),
      row("Buy & hold", bh),
      row("Vol-matched buy & hold (ex-post)", v.vol_matched_bh),
    ]);

    const st = v.stats, dsr = st.deflated_sharpe_insample;
    document.getElementById("stats").innerHTML = [
      ["DSR (in-sample best)", fmt(dsr.dsr, 3), dsr.n_trials + " trials · SR₀ " + fmt(dsr.sr0_annualized) + " ann."],
      ["PSR OOS vs 0", fmt(st.psr_oos_vs_zero, 3), "P(true Sharpe > 0)"],
      ["PSR OOS vs B&H", fmt(st.psr_oos_vs_bh_sharpe, 3), "P(true Sharpe > B&H Sharpe)"],
    ].map(([l, val, sub]) => '<div class="card"><div class="label">' + esc(l) + '</div><div class="value">' + val + '</div><div class="sub">' + esc(sub) + "</div></div>").join("");

    table("ablTable", ["Variant", "Sharpe", "CAGR", "Max DD", "Calmar", "Final NAV", "Turnover/yr"],
      v.ablation.map((a) => [esc(a.label), fmt(a.sharpe), pct(a.cagr, 2), pct(a.max_dd), fmt(a.calmar), fmt(a.final_nav, 2), fmt(a.ann_turnover, 2)]));

    table("subTable", ["Period", "Window", "Strategy return", "Strategy MDD", "B&H return", "B&H MDD"],
      v.subperiods.map((p) => [esc(p.period), esc(p.start + " → " + p.end), pct(p.strategy_return), pct(p.strategy_max_dd), pct(p.bh_return), pct(p.bh_max_dd)]));

    const sens = v.sensitivity;
    setText("sensNote", "Rows: VIX threshold; columns: overheat threshold; other parameters fixed at the in-sample best " +
      JSON.stringify(isb.params) + ". A smooth plateau suggests robustness; an isolated peak suggests over-fitting.");
    const flat = sens.sharpe.flat().filter((x) => x != null);
    const lo = Math.min(...flat), hi = Math.max(...flat);
    document.getElementById("heat").innerHTML =
      "<thead><tr><th>VIX \\ OH</th>" + sens.overheat_threshold.map((o) => "<th>" + fmt(o) + "</th>").join("") + "</tr></thead><tbody>" +
      sens.vix_threshold.map((vx, i) => "<tr><th>" + fmt(vx, 0) + "</th>" +
        sens.sharpe[i].map((x) => '<td style="background:' + heatColor(x, lo, hi) + '">' + fmt(x) + "</td>").join("") + "</tr>").join("") + "</tbody>";

    table("foldTable", ["Test year", "Trained through", "VIX thr", "OH thr", "Earn thr", "w OH", "w Shock", "w Dig", "Train Sharpe", "Test return"],
      v.folds.map((f) => [f.test_year, esc(f.train_end), fmt(f.params.vix_threshold, 0), fmt(f.params.overheat_threshold), fmt(f.params.earn_threshold),
        fmt(f.params.w_overheat), fmt(f.params.w_shock), fmt(f.params.w_digestion), fmt(f.train_sharpe), f.test_return == null ? "live" : pct(f.test_return)]));

    if (health) {
      table("dqTable", ["Check", "Status", "Detail"],
        (health.checks || []).map((c) => [esc(c.name), '<span class="dq ' + esc(c.status) + '">' + esc(c.status) + "</span>", esc(c.detail)]));
      table("srcTable", ["Source", "Latest observation / filing"],
        Object.entries(health.sources || {}).map(([k, d]) => [esc(k), esc(d)]));
    }
    setText("footer", "engine " + (v.engine_version || "—") + (v.git_sha ? " @ " + v.git_sha : "") + " · raw inputs hashed in data/health.json (raw_manifest)");
  }

  boot().catch((e) => setText("footer", "Failed to load: " + e));
})();
