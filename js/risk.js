(function () {
  const { fmt, pct, esc, loadJSON, setText, setHTML, table, renderBanner, chartDefaults } = window.TCD;
  const { t, has, cols } = window.TCD_I18N;

  const signed = (x, d = 2) => (x == null ? "—" : (x >= 0 ? "+" : "") + fmt(x, d));
  const skillKey = (v) => (v.startsWith("skillful") ? "skillful" : v.startsWith("no skill") ? "noskill" : v.startsWith("no demonstrated") ? "nodemo" : "inconclusive");
  const skillTag = (v) => {
    const k = skillKey(v);
    const cls = k === "skillful" ? "PASS" : k === "inconclusive" ? "WARN" : "FAIL";
    return '<span class="dq ' + cls + '" title="' + esc(t("skill.full." + k)) + '">' + esc(t("skill." + k)) + "</span>";
  };
  const epuText = (v) => (/^keep/.test(v) ? t("epu.keep") : /worsens/.test(v) ? t("epu.drop.worse")
    : /one specification/.test(v) ? t("epu.drop.oneSpec") : t("epu.drop.nosig"));
  const modelName = (k, fallback) => (has("model." + k) ? t("model." + k) : fallback || k);
  const live = (m, liveKey) => (m === liveKey ? " <strong>" + esc(t("tag.live")) + "</strong>" : "");
  const pctAxis = (opts) => ({ ...opts.scales.y.ticks, callback: (v) => (v * 100).toFixed(0) + "%" });

  function renderShortTerm(st) {
    if (!st) { document.getElementById("stPanel").hidden = true; return; }
    const so = chartDefaults();
    const c = st.current;
    setText("s-var", pct(c.var95_1d_simple_ret, 1));
    setText("s-var-sub", t("risk.st.varSub", { d: c.date, m: modelName(c.model, c.label) }));
    setText("s-vol1", pct(c.vol_1d_ann, 0));
    setText("s-vol1-sub", t("risk.st.vol1Sub", { d: pct(c.vol_1d, 1), e: pct(c.ewma_vol_ann, 0) }));
    setText("s-vol5", pct(c.vol_5d, 1));
    setText("s-vol5-sub", t("risk.st.vol5Sub", { a: pct(c.vol_5d_ann, 0) }));
    const ret = st.chart.next_day_return, vr = st.chart.var95;
    new Chart(document.getElementById("varChart"), {
      data: {
        labels: st.chart.dates,
        datasets: [
          { type: "bar", label: t("risk.st.ret"), data: ret, backgroundColor: ret.map((v, i) => (v != null && vr[i] != null && v < -vr[i] ? "#8b1e3f" : "rgba(107,101,96,0.45)")), barPercentage: 1, categoryPercentage: 1 },
          { type: "line", label: t("risk.st.varLine"), data: vr.map((v) => (v == null ? null : -v)), borderColor: "#1e3a5f", borderWidth: 1.4, pointRadius: 0 },
        ],
      },
      options: { ...so, scales: { ...so.scales, y: { ...so.scales.y, ticks: pctAxis(so) } } },
    });
    const ev = st.evaluation, liveBt = ev.var95.find((x) => x.model === st.live_model);
    setText("varNote", t("risk.st.varNote", { r: pct(liveBt.rate, 2) }));
    table("stVarTable", cols("risk.st.acc.cols"), ev.variance.map((v) => [t("hz", { h: esc(String(v.horizon)) }), esc(modelName(v.model, v.label)) + live(v.model, st.live_model),
      fmt(v.qlike, 4), fmt(v.corr_vol, 3), v.n]));
    table("stDmTable", cols("risk.st.dm.cols"), ev.dm.map((d) => [t("hz", { h: esc(String(d.horizon)) }), esc(modelName(d.baseline) + " → " + modelName(d.challenger)),
      signed(d.qlike_improvement, 4), signed(d.dm_t, 2),
      d.dm_t >= 2 ? '<span class="dq PASS">' + esc(t("tag.better")) + "</span>" : d.dm_t <= -2 ? '<span class="dq FAIL">' + esc(t("tag.worse")) + "</span>"
        : '<span class="dq WARN">' + esc(t("tag.noSig")) + "</span>"]));
    const pv = (p) => (p < 0.05 ? '<span class="dq FAIL">' : '<span class="dq PASS">') + fmt(p, 3) + "</span>";
    table("stBtTable", cols("risk.st.bt.cols"), ev.var95.map((v) => [esc(modelName(v.model, v.label)) + live(v.model, st.live_model),
      v.breaches + "/" + v.n, pct(v.rate, 2), pv(v.p_value), pv(v.christoffersen.p_value), pct(v.avg_var, 2)]));
    const byQ = ev.var95_by_quantile;
    if (byQ && byQ.insample && byQ.oos) {
      const a = byQ.insample.find((x) => x.model === st.live_model), b = byQ.oos.find((x) => x.model === st.live_model);
      if (a && b) setHTML("qNote", t("risk.st.qNote", { ra: pct(a.rate, 2), pa: fmt(a.p_value, 3), rb: pct(b.rate, 2), pb: fmt(b.p_value, 3) }));
    }
    setHTML("epuNote", t("risk.st.epu", { v: esc(epuText(st.epu_verdict)), spec: esc(t("spec." + st.robustness.spec)), rv: esc(epuText(st.robustness.epu_verdict)) }));
  }

  function renderMarketLive(rv) {
    if (!rv) { setText("mlive-note", t("risk.live.none")); return; }
    const T = rv.targets || {}, a = T.var_1d || {}, b = T.vol_5d || {}, c = T.vol_1m || {}, ch = T.var_1d_challenger || {};
    const v = (x) => esc(t("st.live.v." + (x || "insufficient")));
    const since = (x) => (x.logged_since ? " (" + esc(t("st.live.since", { d: x.logged_since })) + ")" : "");
    const rows = [
      [esc(t("risk.live.var1d")), esc(String(a.logged || 0)) + since(a), esc(String(a.n || 0)),
        a.breach_rate == null ? "—" : esc(String(a.breaches)) + " · " + pct(a.breach_rate, 1) + (a.rolling ? " (" + t("risk.live.last", { n: esc(String(a.rolling.n)) }) + " " + pct(a.rolling.breach_rate, 1) + ")" : ""),
        a.var_ratio == null ? "—" : fmt(a.var_ratio, 2), "<strong>" + v(a.verdict) + "</strong>"],
      [esc(t("risk.live.varch")), esc(String(ch.logged || 0)) + since(ch), esc(String(ch.n || 0)),
        ch.breach_rate == null ? "—" : esc(String(ch.breaches)) + " · " + pct(ch.breach_rate, 1),
        ch.var_ratio == null ? "—" : fmt(ch.var_ratio, 2), "<strong>" + v(ch.verdict) + "</strong>"],
      [esc(t("risk.live.vol5d")), esc(String(b.logged || 0)) + since(b), esc(String(b.n || 0)), "—",
        b.var_ratio == null ? "—" : fmt(b.var_ratio, 2), esc(t("risk.live.descriptive"))],
      [esc(t("risk.live.vol1m")), esc(String(c.logged || 0)) + since(c), esc(String(c.n || 0)),
        c.band_coverage == null ? "—" : t("risk.live.band", { c: pct(c.band_coverage, 0) }),
        c.mean_log_error == null ? "—" : fmt(Math.exp(c.mean_log_error), 2), "<strong>" + v(c.verdict) + "</strong>"],
    ];
    table("mliveTable", cols("risk.live.cols"), rows);
    const st = rv.settings || {};
    const cc = rv.challenger_comparison || {};
    setHTML("mlive-note", t("risk.live.note", { d: esc(String(st.min_days_var)), m: esc(String(st.min_months_vol)), r: esc(String(st.rolling_days)) }) + " " +
      t("risk.live.chnote", { n: esc(String(cc.common_days || 0)), dec: esc(t("risk.live.dec." + (cc.decision || "insufficient"))) }));
  }

  async function boot() {
    const [r, health, mrev] = await Promise.all([loadJSON("data/risk.json"), loadJSON("data/health.json").catch(() => null),
      loadJSON("data/forecast_review_market.json").catch(() => null)]);
    renderMarketLive(mrev);
    document.body.dataset.ready = "1";
    renderBanner(health);
    setHTML("asof-line", t("risk.asof", { asof: esc(r.as_of) }));

    const vf = r.vol_forecast, vcur = vf.current.provisional || vf.current.month_end;
    const t0 = r.targets[0], cur0 = t0.current.provisional || t0.current.month_end;
    const skill = skillKey(t0.verdict) === "skillful";

    setHTML("summary", t("risk.summary", { r2: fmt(vf.oos_r2_vs_mean, 2), beats: t(skill ? "risk.beats.yes" : "risk.beats.no"),
      tail: skill ? "" : t("risk.summary.tail") }));

    renderShortTerm(r.short_term);

    setText("r-vol", pct(vcur.vol, 0));
    setText("r-vol-sub", t("risk.lt.volSub", { lo: pct(vcur.band90[0], 0), hi: pct(vcur.band90[1], 0), c: pct(vcur.current_rv21, 0), d: vcur.date }));
    setText("r-dd", pct(skill ? cur0.p : t0.current.base_rate, 0));
    setText("r-dd-sub", skill ? t("risk.lt.ddSubModel", { lo: pct(cur0.ci90[0], 0), hi: pct(cur0.ci90[1], 0) })
      : t("risk.lt.ddSubBase", { n: t0.current.fit_rows, e: t0.current.fit_events }));
    setText("r-model", pct(cur0.p, 0));
    setText("r-model-sub", t("risk.lt.modelSub", { lo: pct(cur0.ci90[0], 0), hi: pct(cur0.ci90[1], 0), d: cur0.date }) + (skill ? "" : t("risk.lt.modelSubNo")));

    const opts = chartDefaults();
    new Chart(document.getElementById("volChart"), {
      type: "line",
      data: {
        labels: vf.series.dates,
        datasets: [
          { label: t("risk.vf.f"), data: vf.series.forecast, borderColor: "#1e3a5f", borderWidth: 1.6, pointRadius: 0 },
          { label: t("risk.vf.r"), data: vf.series.realized, borderColor: "#8b1e3f", borderWidth: 1, pointRadius: 0 },
        ],
      },
      options: { ...opts, scales: { ...opts.scales, y: { ...opts.scales.y, type: "logarithmic", ticks: pctAxis(opts) } } },
    });
    setText("volNote", t("risk.vf.note", { r2: fmt(vf.oos_r2_vs_mean, 2), rp: signed(vf.oos_r2_vs_persistence), c: fmt(vf.corr_pred_realized, 2),
      w: vf.window.replace("->", "→") }));

    const rows = [];
    r.targets.forEach((tg) => {
      [["full", "risk.sk.full"], ["vol_only", "risk.sk.vol"]].forEach(([k, lbl]) => {
        const e = tg.evaluation[k];
        rows.push([esc(t("risk.sk.target", { h: tg.horizon, c: Math.round(tg.cut * 100) })), esc(t(lbl)), e.events + "/" + e.n, fmt(e.brier, 3),
          fmt(e.brier_climatology, 3), signed(e.bss), "[" + signed(e.bss_ci90[0]) + ", " + signed(e.bss_ci90[1]) + "]", fmt(e.auc, 2),
          k === "full" ? skillTag(tg.verdict) : ""]);
      });
    });
    table("skillTable", cols("risk.sk.cols"), rows);

    table("eraTable", cols("risk.era.cols"), t0.era_evaluation.map((e) => [esc(e.era), e.n, e.events, e.episodes, fmt(e.auc, 2), signed(e.bss)]));

    const pick = document.getElementById("tgtPick");
    r.targets.forEach((tg, i) => {
      const o = document.createElement("option");
      o.value = i;
      o.textContent = has("risk.target." + tg.id) ? t("risk.target." + tg.id) : tg.label;
      pick.appendChild(o);
    });
    let pc = null, rc = null;
    function draw(i) {
      const tg = r.targets[i], s = tg.series;
      if (pc) pc.destroy();
      pc = new Chart(document.getElementById("probChart"), {
        data: {
          labels: s.dates,
          datasets: [
            { type: "bar", label: t("risk.pr.event"), data: s.y, backgroundColor: "rgba(139,30,63,0.18)", barPercentage: 1, categoryPercentage: 1 },
            { type: "line", label: t("risk.pr.model"), data: s.p_model, borderColor: "#1e3a5f", borderWidth: 1.6, pointRadius: 0 },
            { type: "line", label: t("risk.pr.base"), data: s.p_clim, borderColor: "#6b6560", borderDash: [4, 3], borderWidth: 1.2, pointRadius: 0 },
          ],
        },
        options: { ...opts, scales: { ...opts.scales, y: { ...opts.scales.y, min: 0, max: 1, ticks: pctAxis(opts) } } },
      });
      const rel = tg.evaluation.full.reliability.filter((b) => b.n > 0);
      if (rc) rc.destroy();
      rc = new Chart(document.getElementById("relChart"), {
        type: "scatter",
        data: {
          datasets: [
            { label: t("risk.rel.obs"), data: rel.map((b) => ({ x: b.mean_pred, y: b.observed })), backgroundColor: "#1e3a5f", pointRadius: rel.map((b) => 3 + Math.sqrt(b.n)) },
            { label: t("risk.rel.perfect"), type: "line", data: [{ x: 0, y: 0 }, { x: 1, y: 1 }], borderColor: "#6b6560", borderDash: [4, 3], pointRadius: 0 },
          ],
        },
        options: {
          ...opts,
          interaction: { mode: "nearest", intersect: true },
          scales: {
            x: { type: "linear", min: 0, max: 1, title: { display: true, text: t("risk.rel.x") }, ticks: { ...opts.scales.x.ticks, callback: (v) => (v * 100).toFixed(0) + "%" } },
            y: { min: 0, max: 1, title: { display: true, text: t("risk.rel.y") }, ticks: pctAxis(opts) },
          },
        },
      });
      table("relTable", cols("risk.rel.cols"), tg.evaluation.full.reliability.map((b) => [esc(b.bin), b.n, pct(b.mean_pred, 1), pct(b.observed, 1)]));
      const c = tg.current.provisional || tg.current.month_end;
      table("drvTable", cols("risk.drv.cols"), Object.keys(c.features).map((f) => [esc(has("feat." + f) ? t("feat." + f) : f),
        fmt(c.features[f], 3), signed(tg.current.coef[f]), signed(c.contributions_logodds[f])]));
    }
    pick.addEventListener("change", () => draw(+pick.value));
    draw(0);

    setText("footer", t("risk.footer", { ver: r.engine_version || "—" }));
  }

  boot().catch((e) => setText("footer", t("common.failed", { err: e })));
})();
