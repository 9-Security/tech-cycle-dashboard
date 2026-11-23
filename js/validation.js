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

  const PARAM_LABELS = {
    vix_threshold: "VIX thr", overheat_threshold: "OH thr", earn_threshold: "Earn thr", w_overheat: "w OH", w_shock: "w Shock",
    w_digestion: "w Dig", c_px: "c PxExt", c_pe: "c P/E", c_capex: "c Capex", base: "Base", earn_cut: "Earn cut",
    vol_input: "Vol input", vol_target: "Vol target",
  };
  const SKIP_PARAMS = new Set(["w_normal", "band"]);
  const fmtParam = (x) => (x == null ? "off" : typeof x === "number" ? fmt(x, Math.abs(x) >= 10 ? 0 : 2) : esc(x));

  function renderModel(r) {
    const s = r.summary, oos = r.oos, bh = r.bh, isb = r.insample_best;
    const verdict = oos.sharpe >= bh.sharpe
      ? "The out-of-sample strategy matched or beat buy &amp; hold on Sharpe (" + fmt(oos.sharpe) + " vs " + fmt(bh.sharpe) + "), at " + pct(oos.ann_vol) + " vs " + pct(bh.ann_vol) + " volatility."
      : "The out-of-sample strategy <strong>under-performed</strong> buy &amp; hold on Sharpe (" + fmt(oos.sharpe) + " vs " + fmt(bh.sharpe) +
        "). The in-sample-tuned version looks far better (" + fmt(isb.full_sample.sharpe) + " full sample) — that gap is hindsight, not skill.";
    document.getElementById("summary").innerHTML =
      "<strong>" + esc(r.model ? r.model.label : "Model") + ".</strong> " +
      "<strong>Out-of-sample window:</strong> " + esc(s.oos_start) + " → " + esc(s.oos_end) + " (" + s.oos_months + " months). " +
      "<strong>Search space:</strong> " + s.grid_size + " configurations. <strong>Objective:</strong> " + esc(s.objective) + ". " +
      "<strong>Refit:</strong> " + esc(s.refit) + ", training from " + esc(s.train_start) + ".<br/><br/>" + verdict;

    const row = (label, m) => [esc(label), fmt(m.sharpe), pct(m.cagr, 2), pct(m.ann_vol), pct(m.max_dd), fmt(m.calmar), fmt(m.final_nav, 2), fmt(m.avg_weight, 2)];
    table("cmpTable", ["Track", "Sharpe", "CAGR", "Vol", "Max DD", "Calmar", "Final NAV", "Avg weight"], [
      row("Walk-forward strategy (OOS)", oos),
      row("In-sample best, same window (hindsight)", isb.on_oos_window),
      row("Buy & hold", bh),
      row("Vol-matched buy & hold (ex-post)", r.vol_matched_bh),
    ]);

    const st = r.stats, dsr = st.deflated_sharpe_insample;
    document.getElementById("stats").innerHTML = [
      ["DSR (in-sample best)", fmt(dsr.dsr, 3), dsr.n_trials + " trials · SR₀ " + fmt(dsr.sr0_annualized) + " ann."],
      ["PSR OOS vs 0", fmt(st.psr_oos_vs_zero, 3), "P(true Sharpe > 0)"],
      ["PSR OOS vs B&H", fmt(st.psr_oos_vs_bh_sharpe, 3), "P(true Sharpe > B&H Sharpe)"],
    ].map(([l, val, sub]) => '<div class="card"><div class="label">' + esc(l) + '</div><div class="value">' + val + '</div><div class="sub">' + esc(sub) + "</div></div>").join("");

    table("ablTable", ["Variant", "Sharpe", "CAGR", "Max DD", "Calmar", "Final NAV", "Turnover/yr"],
      r.ablation.map((a) => [esc(a.label), fmt(a.sharpe), pct(a.cagr, 2), pct(a.max_dd), fmt(a.calmar), fmt(a.final_nav, 2), fmt(a.ann_turnover, 2)]));

    table("subTable", ["Period", "Window", "Strategy return", "Strategy MDD", "B&H return", "B&H MDD"],
      r.subperiods.map((p) => [esc(p.period), esc(p.start + " → " + p.end), pct(p.strategy_return), pct(p.strategy_max_dd), pct(p.bh_return), pct(p.bh_max_dd)]));

    const sens = r.sensitivity;
    const xn = sens.x_name || "overheat_threshold", yn = sens.y_name || "vix_threshold";
    const xs = sens.x_values || sens.overheat_threshold, ys = sens.y_values || sens.vix_threshold;
    setText("sensNote", "Rows: " + (PARAM_LABELS[yn] || yn) + "; columns: " + (PARAM_LABELS[xn] || xn) + "; other parameters fixed at the in-sample best " +
      Object.entries(isb.params).map(([k, x]) => k + "=" + (x == null ? "off" : x)).join(", ") + ". A smooth plateau suggests robustness; an isolated peak suggests over-fitting.");
    const flat = sens.sharpe.flat().filter((x) => x != null);
    const lo = Math.min(...flat), hi = Math.max(...flat);
    document.getElementById("heat").innerHTML =
      "<thead><tr><th>" + esc((PARAM_LABELS[yn] || yn) + " \\ " + (PARAM_LABELS[xn] || xn)) + "</th>" + xs.map((o) => "<th>" + fmtParam(o) + "</th>").join("") + "</tr></thead><tbody>" +
      ys.map((yv, i) => "<tr><th>" + fmtParam(yv) + "</th>" +
        sens.sharpe[i].map((x) => '<td style="background:' + heatColor(x, lo, hi) + '">' + fmt(x) + "</td>").join("") + "</tr>").join("") + "</tbody>";

    const keys = Object.keys(r.folds[0].params).filter((k) => !SKIP_PARAMS.has(k) && !(k === "earn_threshold" && "earn_cut" in r.folds[0].params));
    table("foldTable", ["Test year", "Trained through"].concat(keys.map((k) => PARAM_LABELS[k] || k), ["Train Sharpe", "Test return"]),
      r.folds.map((f) => [f.test_year, esc(f.train_end)].concat(keys.map((k) => fmtParam(f.params[k])),
        [fmt(f.train_sharpe), f.test_return == null ? "live" : pct(f.test_return)])));
  }

  async function boot() {
    const [v, health] = await Promise.all([loadJSON("data/validation.json"), loadJSON("data/health.json").catch(() => null)]);
    document.body.dataset.ready = "1";
    renderBanner(health);
    document.getElementById("asof-line").innerHTML = "Nested walk-forward · as of <strong>" + esc(v.as_of) + "</strong>";

    // Model comparison (always visible)
    const row = (label, m) => [esc(label), fmt(m.sharpe), pct(m.cagr, 2), pct(m.ann_vol), pct(m.max_dd), fmt(m.calmar), fmt(m.final_nav, 2), fmt(m.avg_weight, 2)];
    table("modelTable", ["Model (OOS " + esc(v.summary.oos_start) + " → " + esc(v.summary.oos_end) + ")", "Sharpe", "CAGR", "Vol", "Max DD", "Calmar", "Final NAV", "Avg weight"],
      (v.model_comparison || []).map((m) => row(m.label, m)));
    const cand = v.candidate;
    if (cand) {
      const sd = cand.since_design;
      setText("designNote", "v3 was designed on " + cand.design_date + " after seeing the full-sample signal study, so its walk-forward numbers above are still " +
        "optimistic. Only months after the design date are a clean test" +
        (sd ? ": " + sd.months + " month(s) so far, v3 " + pct(sd.v3.period_return) + " vs B&H " + pct(sd.bh.period_return) + "." : ": none yet."));
    }

    const valRows = (v.valuation_comparison || []);
    const vlabel = { pe: "Aggregate P/E (default)", price_ext: "Price extension proxy (v2.0)" };
    table("valTable", ["Valuation input (v2 model)", "OOS Sharpe", "OOS Max DD", "OOS Final NAV", "Overheat months (OOS)", "IC vs next 12m", "IC window"],
      valRows.map((r) => [esc(vlabel[r.valuation] || r.valuation), fmt(r.oos_sharpe), pct(r.oos_max_dd), fmt(r.oos_final_nav, 2),
        r.overheat_months_oos, fmt(r.ic_val_z_fwd12m, 3), esc(r.ic_window || "—")]));

    const reports = { regime_v2: v, tilt_v3: cand };
    const buttons = document.querySelectorAll("#modelPick button");
    buttons.forEach((b) => {
      b.disabled = !reports[b.dataset.model];
      b.addEventListener("click", () => {
        buttons.forEach((x) => x.classList.toggle("active", x === b));
        renderModel(reports[b.dataset.model]);
      });
    });
    renderModel(v);

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
