(function () {
  const { fmt, esc, loadJSON, setText, renderBanner, regimeBadge } = window.TCD;

  async function boot() {
    const [status, sc, health] = await Promise.all([
      loadJSON("data/status.json"),
      loadJSON("data/scenarios.json"),
      loadJSON("data/health.json").catch(() => null),
    ]);
    document.body.dataset.ready = "1";
    renderBanner(health);

    document.getElementById("asof-line").innerHTML =
      "Rule-based risk brief · lag-1 engine · not trade signals · as of <strong>" + esc(status.as_of) + "</strong>";

    const w = status.weights || {};
    document.getElementById("m-regime").innerHTML = regimeBadge(status.regime);
    setText("m-regime-sub", "month-end " + status.panel_end);
    setText("m-weight", fmt(w.executed_weight, 2));
    setText("m-weight-sub", "held through " + (w.in_force_month || "—"));
    const prov = status.provisional;
    if (prov) {
      document.getElementById("m-prov").innerHTML = regimeBadge(prov.regime);
      setText("m-prov-sub", "data through " + prov.data_through);
    } else {
      setText("m-prov-sub", "no month in progress");
    }
    setText("m-fit", status.params ? String(status.params.fit_for_year) : "—");
    setText("interpretation", sc.interpretation || "");

    const trig = document.getElementById("trigTable");
    trig.innerHTML = "<thead><tr><th>Trigger</th><th>Signal</th><th>Value</th><th>Threshold</th><th>Fires when</th><th>Distance</th><th>Status</th><th>Weight if active</th></tr></thead><tbody>" +
      (sc.triggers || []).map((t) =>
        "<tr><td>" + esc(t.id) + "</td><td>" + esc(t.signal) + "</td><td>" + fmt(t.value) + "</td><td>" + fmt(t.threshold) +
        "</td><td>" + esc(t.direction) + "</td><td>" + fmt(t.distance) + "</td><td>" +
        (t.active ? '<span class="dq FAIL">ACTIVE</span>' : '<span class="dq PASS">inactive</span>') +
        "</td><td>" + fmt(t.weight, 2) + "</td></tr>").join("") + "</tbody>";

    const grid = document.getElementById("scenarioGrid");
    (sc.scenarios || []).forEach((s) => {
      const el = document.createElement("article");
      el.className = "scenario-card " + s.id;
      const posture = s.suggested_defensive_posture || {};
      const flips = (s.flip_conditions || []).map((f) => "<li>" + esc(f) + "</li>").join("");
      el.innerHTML = "<h3>" + esc(s.id) + " <span class='muted small'>(" + esc(s.horizon) + ")</span></h3>" +
        "<p>" + esc(s.thesis) + "</p>" + (flips ? "<ul>" + flips + "</ul>" : "") +
        "<p>Risk weight: <span class='weight'>" + fmt(posture.risk_weight, 2) + "</span></p>" +
        "<p class='muted small'>" + esc(posture.rationale) + "</p>";
      grid.appendChild(el);
    });
    setText("disclaimer", sc.disclaimer || "Not investment advice.");
    setText("footer", "Snapshot: " + (sc.snapshot_label || "") + " · as_of " + status.as_of + " · DATA_SOURCE=" + (status.DATA_SOURCE || "REAL"));
  }

  boot().catch((e) => setText("footer", "Failed to load: " + e));
})();
