(function () {
  const fmt = (x, d = 2) =>
    x == null || Number.isNaN(Number(x)) ? "—" : Number(x).toFixed(d);

  async function loadJSON(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(path + " → " + res.status);
    return res.json();
  }

  async function boot() {
    const [status, scenarios] = await Promise.all([
      loadJSON("data/status.json"),
      loadJSON("data/scenarios.json"),
    ]);

    document.body.dataset.ready = "1";

    const asOf = status.as_of || scenarios.as_of || "—";
    const regime = (status.regime && status.regime.label) || "—";
    const regimeCode = (status.regime && status.regime.code) || "—";
    const weights = status.weights || scenarios.weights || {};
    const signals = status.signals || scenarios.signals || {};

    document.getElementById("asof-line").innerHTML =
      "3–6 month risk narratives · lag-1 engine · not trade signals · as of <strong>" +
      asOf +
      "</strong> · live regime: <strong>" +
      regime +
      "</strong>";

    document.getElementById("m-asof").textContent = asOf;
    document.getElementById("m-asof-sub").textContent =
      (status.DATA_SOURCE || status.data_source || "REAL") +
      " · panel " +
      (status.panel_end || scenarios.panel_end || "—");
    document.getElementById("m-regime").textContent = regime;
    document.getElementById("m-regime-sub").textContent = "code " + regimeCode;
    document.getElementById("m-weight").textContent = fmt(
      weights.recommended_weight ?? weights.executed_weight,
      4
    );
    document.getElementById("m-weight-sub").textContent =
      "target " + fmt(weights.target_weight, 1);
    document.getElementById("m-vix").textContent =
      fmt(signals.vix, 2) + " · " + fmt(signals.overheat_score, 3);
    document.getElementById("m-vix-sub").textContent =
      "shock_flag " + (signals.shock_flag ?? "—");

    document.getElementById("interpretation").textContent =
      scenarios.interpretation || "";

    const grid = document.getElementById("scenarioGrid");
    (scenarios.scenarios || []).forEach(function (s) {
      const el = document.createElement("article");
      el.className = "scenario-card " + s.id;
      const posture = s.suggested_defensive_posture || {};
      const flips = (s.flip_conditions || [])
        .map(function (f) {
          return "<li>" + f + "</li>";
        })
        .join("");
      el.innerHTML =
        "<h3>" +
        s.id +
        " <span style='font-weight:500;color:#6b6560;font-size:0.8rem'>(" +
        (s.horizon || "3-6 months") +
        ")</span></h3>" +
        "<p>" +
        (s.thesis || "") +
        "</p>" +
        (flips ? "<ul>" + flips + "</ul>" : "") +
        "<p>Suggested defensive posture: <span class='weight'>" +
        fmt(posture.risk_weight, 4) +
        "</span></p>" +
        "<p style='color:#6b6560;font-size:0.8rem'>" +
        (posture.rationale || "") +
        "</p>";
      grid.appendChild(el);
    });

    document.getElementById("disclaimer").textContent =
      scenarios.disclaimer ||
      "Scenario analysis for risk discussion only. Not investment advice. Not an auto-trading signal.";

    document.getElementById("footer").textContent =
      "Snapshot: " +
      (scenarios.snapshot_label || "baked scenario brief") +
      " · as_of " +
      asOf +
      " · DATA_SOURCE=" +
      (scenarios.DATA_SOURCE || status.DATA_SOURCE || "REAL");
  }

  boot().catch(function (e) {
    document.getElementById("footer").textContent = "Failed to load: " + e;
  });
})();
