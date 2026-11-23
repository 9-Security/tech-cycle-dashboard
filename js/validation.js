(function () {
  const { fmt, pct, esc, loadJSON, setText, setHTML, table, renderBanner } = window.TCD;
  const { t, has, cols } = window.TCD_I18N;

  function heatColor(v, lo, hi) {
    if (v == null) return "#eee";
    const k = hi > lo ? (v - lo) / (hi - lo) : 0.5;
    const r = Math.round(196 + (47 - 196) * k), g = Math.round(92 + (111 - 92) * k), b = Math.round(38 + (78 - 38) * k);
    return "rgba(" + r + "," + g + "," + b + ",0.55)";
  }
  const SKIP_PARAMS = new Set(["w_normal", "band"]);
  const fmtParam = (x) => (x == null ? t("off") : typeof x === "number" ? fmt(x, Math.abs(x) >= 10 ? 0 : 2) : esc(x));
  const pname = (k) => (has("param." + k) ? t("param." + k) : k);
  const metricRow = (label, m) => [esc(label), fmt(m.sharpe), pct(m.cagr, 2), pct(m.ann_vol), pct(m.max_dd), fmt(m.calmar), fmt(m.final_nav, 2), fmt(m.avg_weight, 2)];
  const tagState = (p) => '<span class="dq ' + (p === true ? "PASS" : p === false ? "FAIL" : "WARN") + '">' +
    esc(t(p === true ? "tag.pass" : p === false ? "tag.fail" : "tag.pending")) + "</span>";

  function ablLabel(a, isTilt) {
    if (a.variant === "vol_matched_bh") {
      const m = /([\d.]+) risk \/ ([\d.]+) cash/.exec(a.label || "");
      return t("abl.vol_matched_bh", { c: m ? m[1] : "?", k: m ? m[2] : "?" });
    }
    if (a.variant === "full") return t(isTilt ? "abl.tilt.full" : "abl.full");
    return has("abl." + a.variant) ? t("abl." + a.variant) : a.label;
  }

  function promoDetail(c) {
    const d = c.detail || "";
    if (/^needs/.test(d)) return t("promo.d.needs2");
    if (d === "fingerprint matches") return t("promo.d.fpOk");
    if (/^changed/.test(d)) return t("promo.d.fpChanged");
    if (d === "no history") return t("promo.d.noHistory");
    const g = /^longest gap (\d+) d$/.exec(d);
    if (g) return t("promo.d.gap", { n: g[1] });
    return d; // numeric comparisons ("0/24", "0.46 vs 0.39") read the same in both languages
  }

  function renderModel(r, cfg) {
    const s = r.summary, oos = r.oos, bh = r.bh, isb = r.insample_best;
    const isTilt = r.model && r.model.key === "tilt_v3";
    const verdict = oos.sharpe >= bh.sharpe
      ? t("val.verdict.good", { s: fmt(oos.sharpe), bh: fmt(bh.sharpe), v: pct(oos.ann_vol), bv: pct(bh.ann_vol) })
      : t("val.verdict.bad", { s: fmt(oos.sharpe), bh: fmt(bh.sharpe), is: fmt(isb.full_sample.sharpe) });
    const bt = (cfg && cfg.backtest) || {};
    setHTML("summary", t("val.summary", {
      model: esc(t("val.model.label." + (r.model ? r.model.key : "regime_v2"))), a: esc(s.oos_start), b: esc(s.oos_end), n: s.oos_months,
      grid: s.grid_size, pen: fmt(bt.mdd_penalty, 1), budget: pct(bt.mdd_budget, 0), train: esc(s.train_start), verdict: verdict }));

    table("cmpTable", [t("val.cmp.col0")].concat(cols("val.cols.metrics")), [
      metricRow(t("val.cmp.oos"), oos), metricRow(t("val.cmp.is"), isb.on_oos_window),
      metricRow(t("val.cmp.bh"), bh), metricRow(t("val.cmp.vm"), r.vol_matched_bh)]);

    const st = r.stats, dsr = st.deflated_sharpe_insample;
    setHTML("stats", [
      [t("val.stats.dsr"), fmt(dsr.dsr, 3), t("val.stats.dsrSub", { n: dsr.n_trials, sr: fmt(dsr.sr0_annualized) })],
      [t("val.stats.psr0"), fmt(st.psr_oos_vs_zero, 3), t("val.stats.psr0Sub")],
      [t("val.stats.psrbh"), fmt(st.p_sharpe_gt_bh != null ? st.p_sharpe_gt_bh : st.psr_oos_vs_bh_sharpe, 3), t("val.stats.psrbhSub")],
    ].map(([l, val, sub]) => '<div class="card"><div class="label">' + esc(l) + '</div><div class="value">' + val + '</div><div class="sub">' + esc(sub) + "</div></div>").join(""));

    const ac = cols("val.abl.cols");
    table("ablTable", ac, r.ablation.map((a) => [esc(ablLabel(a, isTilt)), fmt(a.sharpe), pct(a.cagr, 2), pct(a.max_dd), fmt(a.calmar), fmt(a.final_nav, 2), fmt(a.ann_turnover, 2)]));

    table("subTable", cols("val.sub.cols"), r.subperiods.map((p) => [esc(has("period." + p.period) ? t("period." + p.period) : p.period),
      esc(p.start + " → " + p.end), pct(p.strategy_return), pct(p.strategy_max_dd), pct(p.bh_return), pct(p.bh_max_dd)]));

    const sens = r.sensitivity;
    const xn = sens.x_name || "overheat_threshold", yn = sens.y_name || "vix_threshold";
    const xs = sens.x_values || sens.overheat_threshold, ys = sens.y_values || sens.vix_threshold;
    setText("sensNote", t("val.sens.note", { y: pname(yn), x: pname(xn),
      params: Object.entries(isb.params).map(([k, x]) => k + "=" + (x == null ? t("off") : x)).join(", ") }));
    const flat = sens.sharpe.flat().filter((x) => x != null);
    const lo = Math.min(...flat), hi = Math.max(...flat);
    setHTML("heat", "<thead><tr><th>" + esc(pname(yn) + " \\ " + pname(xn)) + "</th>" + xs.map((o) => "<th>" + fmtParam(o) + "</th>").join("") + "</tr></thead><tbody>" +
      ys.map((yv, i) => "<tr><th>" + fmtParam(yv) + "</th>" +
        sens.sharpe[i].map((x) => '<td style="background:' + heatColor(x, lo, hi) + '">' + fmt(x) + "</td>").join("") + "</tr>").join("") + "</tbody>");

    const p0 = r.folds[0].params;
    const keys = Object.keys(p0).filter((k) => !SKIP_PARAMS.has(k) && !(k === "earn_threshold" && "earn_cut" in p0));
    table("foldTable", [t("val.folds.c0"), t("val.folds.c1")].concat(keys.map(pname), [t("val.folds.trainSharpe"), t("val.folds.testReturn")]),
      r.folds.map((f) => [f.test_year, esc(f.train_end)].concat(keys.map((k) => fmtParam(f.params[k])),
        [fmt(f.train_sharpe), f.test_return == null ? esc(t("val.folds.live")) : pct(f.test_return)])));
  }

  function renderCross(x) {
    if (!x) return;
    document.getElementById("xmPanel").hidden = false;
    const vd = x.verdict, p = x.pooled, cr = x.criteria;
    const sgn = (z) => (z >= 0 ? "+" : "") + fmt(z, 3);
    setHTML("xmVerdict", t(vd.overall_pass ? "xm.verdict.pass" : "xm.verdict.fail", { n: vd.n_sharpe, m: vd.n_markets,
      d: sgn(p.mean_sharpe_diff), lo: sgn(p.ci[0]), hi: sgn(p.ci[1]), reg: esc(cr.registered) }));
    const tag = (ok) => '<span class="dq ' + (ok ? "PASS" : "FAIL") + '">' + esc(t(ok ? "tag.pass" : "tag.fail")) + "</span>";
    table("xmCrit", cols("xm.crit.cols"), [
      ["C1", esc(t("xm.C1", { k: cr.C1_min_markets_sharpe })), tag(vd.C1.pass), esc(t("xm.d.C1", { n: vd.n_sharpe, m: vd.n_markets }))],
      ["C2", esc(t("xm.C2")), tag(vd.C2.pass), esc(t("xm.d.C2", { d: sgn(p.mean_sharpe_diff), lo: sgn(p.ci[0]), hi: sgn(p.ci[1]) }))],
      ["C3", esc(t("xm.C3", { k: cr.C3_min_markets_mdd })), tag(vd.C3.pass), esc(t("xm.d.C1", { n: vd.n_mdd, m: vd.n_markets }))],
    ]);
    table("xmTable", cols("xm.cols"), x.markets.map((r) => [
      esc(has("mkt." + r.symbol) ? t("mkt." + r.symbol) : r.name), esc(r.oos_start.slice(0, 7) + " → " + r.oos_end.slice(0, 7)),
      fmt(r.v3_sharpe), fmt(r.bh_sharpe),
      '<span class="dq ' + (r.sharpe_diff > 0 ? "PASS" : "FAIL") + '">' + (r.sharpe_diff >= 0 ? "+" : "") + fmt(r.sharpe_diff, 2) + "</span>",
      pct(r.v3_max_dd), pct(r.vm_max_dd), pct(r.v3_cagr), pct(r.bh_cagr), fmt(r.avg_weight)]));
  }

  async function boot() {
    const [v, health, cross] = await Promise.all([loadJSON("data/validation.json"), loadJSON("data/health.json").catch(() => null),
      loadJSON("data/cross_market.json").catch(() => null)]);
    renderCross(cross);
    document.body.dataset.ready = "1";
    renderBanner(health);
    setHTML("asof-line", t("val.asof", { asof: esc(v.as_of) }));

    table("modelTable", [t("val.models.col0", { a: v.summary.oos_start, b: v.summary.oos_end })].concat(cols("val.cols.metrics")),
      (v.model_comparison || []).map((m) => metricRow(has("val.model." + m.model) ? t("val.model." + m.model) : m.label, m)));

    const cand = v.candidate;
    if (cand) {
      const sd = cand.since_design;
      setText("designNote", sd
        ? t("val.design.some", { d: cand.design_date, n: sd.months, v3: pct(sd.v3.period_return), bh: pct(sd.bh.period_return) })
        : t("val.design.none", { d: cand.design_date }));
      const pr = cand.promotion;
      if (pr) {
        const rule = (v.config && v.config.promotion) || {};
        const notes = {
          collecting: t("promo.note.collecting", { n: pr.months, min: pr.min_months, earliest: pr.earliest_decision_after }),
          eligible: t("promo.note.eligible"),
          not_met: t("promo.note.not_met", { retire: pr.retire_after }),
          retire: t("promo.note.retire", { r: rule.retire_months || 36 }),
          invalid: t("promo.note.invalid"),
        };
        setHTML("promoState", t("val.promo.state", { state: esc(t("promo.state." + pr.state)), note: esc(notes[pr.state] || pr.note),
          first: esc(pr.first_month), earliest: esc(pr.earliest_decision_after), retire: esc(pr.retire_after) }));
        const names = {
          C1: t("promo.C1", { min: pr.min_months }), C2: t("promo.C2"), C3: t("promo.C3", { tol: pct(rule.mdd_tolerance, 0) }),
          C4: t("promo.C4"), C5: t("promo.C5"), C6: t("promo.C6", { d: rule.max_refresh_gap_days }),
        };
        table("promoTable", cols("val.promo.cols"), pr.criteria.map((c) => [esc(c.id), esc(names[c.id] || c.name),
          tagState(c.id === "C1" && pr.state === "collecting" ? null : c.pass), esc(promoDetail(c))]));
      }
    }

    table("valTable", cols("val.valin.cols"), (v.valuation_comparison || []).map((r) => [
      esc(has("val.valin." + r.valuation) ? t("val.valin." + r.valuation) : r.valuation), fmt(r.oos_sharpe), pct(r.oos_max_dd), fmt(r.oos_final_nav, 2),
      r.overheat_months_oos, fmt(r.ic_val_z_fwd12m, 3), esc((r.ic_window || "—").replace("->", "→"))]));

    const reports = { regime_v2: v, tilt_v3: cand };
    const buttons = document.querySelectorAll("#modelPick button");
    buttons.forEach((b) => {
      b.disabled = !reports[b.dataset.model];
      b.addEventListener("click", () => {
        buttons.forEach((x) => x.classList.toggle("active", x === b));
        renderModel(reports[b.dataset.model], v.config);
      });
    });
    renderModel(v, v.config);

    if (health) {
      table("dqTable", cols("val.dq.cols"), (health.checks || []).map((c) => [esc(has("dq." + c.name) ? t("dq." + c.name) : c.name),
        '<span class="dq ' + esc(c.status) + '">' + esc(c.status) + "</span>", esc(c.detail)]));
      table("srcTable", cols("val.src.cols"), Object.entries(health.sources || {}).map(([k, d]) => [esc(k), esc(d)]));
    }
    setText("footer", t("val.footer", { ver: v.engine_version || "—", sha: v.git_sha ? " @ " + v.git_sha : "" }));
  }

  boot().catch((e) => setText("footer", t("common.failed", { err: e })));
})();
