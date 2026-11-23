(function () {
  const { fmt, esc, loadJSON, setText, setHTML, table, renderBanner, regimeLabel, regimeBadge, buildScenarios } = window.TCD;
  const { t, cols } = window.TCD_I18N;

  async function boot() {
    const [status, sc, health] = await Promise.all([
      loadJSON("data/status.json"),
      loadJSON("data/scenarios.json"),
      loadJSON("data/health.json").catch(() => null),
    ]);
    document.body.dataset.ready = "1";
    renderBanner(health);
    setHTML("asof-line", t("sc.asof", { asof: esc(status.as_of) }));

    const w = status.weights || {};
    setHTML("m-regime", regimeBadge(status.regime));
    setText("m-regime-sub", t("index.sub.monthEnd", { date: status.panel_end }));
    setText("m-weight", fmt(w.executed_weight, 2));
    setText("m-weight-sub", t("index.sub.heldThrough", { m: w.in_force_month || "—" }));
    const prov = status.provisional;
    if (prov) {
      setHTML("m-prov", regimeBadge(prov.regime));
      setText("m-prov-sub", t("sc.sub.dataThrough", { d: prov.data_through }));
    } else {
      setText("m-prov-sub", t("index.sub.noProv"));
    }
    const fitYear = status.params ? status.params.fit_for_year : null;
    setText("m-fit", fitYear ? String(fitYear) : "—");

    // Interpretation rebuilt from structured status fields.
    let interp = t("sc.interp.official", { date: status.panel_end, regime: regimeLabel(status.regime.code, status.regime.label),
      w: fmt(w.executed_weight, 2), m: w.in_force_month });
    if (prov) interp += t("sc.interp.prov", { m: prov.month, d: prov.data_through, regime: regimeLabel(prov.regime.code, prov.regime.label),
      w: fmt(prov.next_month_weight_if_month_ended_today, 2) });
    interp += t("sc.interp.tail", { y: fitYear ? fitYear - 1 : "—" });
    setText("interpretation", interp);

    table("trigTable", cols("sc.trig.cols"), (sc.triggers || []).map((x) => [
      esc(t("sc.id." + x.id)), esc(t("sc.sig." + x.id)), fmt(x.value), fmt(x.threshold), esc(t("sc.trig." + x.direction)), fmt(x.distance),
      x.active ? '<span class="dq FAIL">' + esc(t("tag.active")) + "</span>" : '<span class="dq PASS">' + esc(t("tag.inactive")) + "</span>",
      fmt(x.weight, 2)]));

    const grid = document.getElementById("scenarioGrid");
    buildScenarios(status, sc).forEach((s) => {
      const el = document.createElement("article");
      el.className = "scenario-card " + s.id;
      el.innerHTML = "<h3>" + esc(t("sc.id." + s.id)) + " <span class='muted small'>(" + esc(t("sc.horizon")) + ")</span></h3>" +
        "<p>" + esc(s.thesis) + "</p><ul>" + s.flips.map((f) => "<li>" + esc(f) + "</li>").join("") + "</ul>" +
        "<p>" + esc(t("sc.weight")) + " <span class='weight'>" + fmt(s.weight, 2) + "</span></p>" +
        "<p class='muted small'>" + esc(s.rationale) + "</p>";
      grid.appendChild(el);
    });
    setText("footer", t("sc.footer", { asof: status.as_of, src: status.DATA_SOURCE || "REAL" }));
  }

  boot().catch((e) => setText("footer", t("common.failed", { err: e })));
})();
