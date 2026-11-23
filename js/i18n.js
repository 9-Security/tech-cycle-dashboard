/* Minimal i18n: English + Traditional Chinese (Taiwan).
 *
 * - Language: ?lang= query > saved choice (localStorage) > browser language > en.
 * - Static text: elements with data-i18n (textContent) or data-i18n-html
 *   (innerHTML; dictionary content only, never data) and data-i18n-title.
 * - Dynamic text: TCD_I18N.t("key", {param}) with {param} placeholders.
 * - Switching reloads the page so every chart and table is rebuilt cleanly.
 */
(function (global) {
  const SUPPORTED = ["en", "zh-TW"];
  const STORE_KEY = "tcd.lang";

  function detect() {
    try {
      const q = new URLSearchParams(location.search).get("lang");
      if (q && SUPPORTED.includes(q)) return q;
    } catch (e) { /* ignore */ }
    try {
      const s = localStorage.getItem(STORE_KEY);
      if (s && SUPPORTED.includes(s)) return s;
    } catch (e) { /* storage blocked */ }
    const nav = (navigator.languages && navigator.languages[0]) || navigator.language || "en";
    return /^zh/i.test(nav) ? "zh-TW" : "en";
  }

  const D = { en: {}, "zh-TW": {} };
  function add(key, en, zh) { D.en[key] = en; D["zh-TW"][key] = zh; }

  // ------------------------------------------------------------ common
  add("site.title", "Tech Cycle", "科技週期");
  add("nav.backtest", "Backtest", "回測");
  add("nav.validation", "Validation", "驗證");
  add("nav.signals", "Signals", "訊號");
  add("nav.risk", "Risk", "風險");
  add("nav.scenarios", "Scenarios", "情境");
  add("lang.switch", "中文", "EN");
  add("lang.switch.title", "切換為繁體中文", "Switch to English");
  add("common.loading", "Loading…", "載入中…");
  add("common.loadingStatus", "Loading data status…", "正在讀取資料狀態…");
  add("common.failed", "Failed to load: {err}", "載入失敗：{err}");
  add("common.disclaimer", "Scenario analysis for risk discussion only. Not investment advice. Not an auto-trading signal.",
    "僅供風險討論的情境分析，非投資建議，也不是自動交易訊號。");
  add("banner.live", "Live data.", "資料為最新。");
  add("banner.stale", "Stale data.", "資料已過期。");
  add("banner.body", "Last refresh {run} · market data through <strong>{through}</strong> · monthly panel through {panel} · DQ {pass}/{total} pass",
    "最後更新 {run} · 市場資料截至 <strong>{through}</strong> · 月度資料截至 {panel} · 資料品質檢查 {pass}/{total} 通過");
  add("banner.staleNote", " · the daily refresh has not succeeded for {days} days.", " · 每日自動更新已 {days} 天未成功。");
  add("regime.1", "Overheat", "過熱");
  add("regime.2", "Shock", "衝擊");
  add("regime.3", "Digestion", "消化");
  add("regime.4", "Normal", "正常");
  add("state.1", "Valuation/Capex cut", "估值／Capex 減碼");
  add("state.2", "Vol-capped", "波動上限減碼");
  add("state.3", "Earnings cut", "獲利減碼");
  add("state.4", "Unconstrained", "未受限");
  add("tag.supports", "supports", "支持");
  add("tag.contradicts", "contradicts", "相反");
  add("tag.inconclusive", "inconclusive", "不確定");
  add("tag.pass", "pass", "通過");
  add("tag.fail", "fail", "未通過");
  add("tag.pending", "pending", "待定");
  add("tag.better", "better", "較佳");
  add("tag.worse", "worse", "較差");
  add("tag.noSig", "no sig. difference", "無顯著差異");
  add("tag.active", "ACTIVE", "已觸發");
  add("tag.inactive", "inactive", "未觸發");
  add("tag.live", "(live)", "（上線）");
  add("unit.months", "{n} months", "{n} 個月");
  add("off", "off", "關閉");

  // -------------------------------------------------------------- light
  add("light.h2", "Today's risk light", "今日風險燈號");
  add("light.title.green", "Green: markets are relatively calm", "綠燈：市場相對平靜");
  add("light.title.yellow", "Yellow: volatility is elevated, stay alert", "黃燈：波動偏高，請留意");
  add("light.title.red", "Red: markets are turbulent, short-term risk is clearly elevated", "紅燈：市場處於動盪期，短期風險明顯偏高");
  add("light.vol.high", "Tomorrow's expected volatility is about {r}× the usual level, higher than on {p} of trading days since {y}. Daily moves of ±{m} are ordinary right now.",
    "預估明天的波動約是平常的 {r} 倍，高於 {y} 年以來 {p} 的交易日。現在單日漲跌 ±{m} 都算正常範圍。");
  add("light.vol.low", "Tomorrow's expected volatility is about {r}× the usual level, lower than on {q} of trading days since {y}. Typical daily moves are around ±{m}.",
    "預估明天的波動約是平常的 {r} 倍，低於 {y} 年以來 {q} 的交易日。目前單日漲跌大約在 ±{m}。");
  add("light.var", "About 1 trading day in 20 could see a loss larger than {v}.", "每 20 個交易日中，大約有 1 天可能跌超過 {v}。");
  add("light.mtd", "Month to date ({m}): {r}.", "本月至今（{m}）：{r}。");
  add("light.val.below", "Valuation is not stretched: aggregate P/E {pe}×, below its 10-year average.", "估值不貴：大型科技股合計本益比 {pe} 倍，低於近 10 年平均。");
  add("light.val.near", "Valuation is near normal: aggregate P/E {pe}×, close to its 10-year average.", "估值接近平常：大型科技股合計本益比 {pe} 倍，接近近 10 年平均。");
  add("light.val.above", "Valuation is elevated: aggregate P/E {pe}×, above its 10-year average.", "估值偏高：大型科技股合計本益比 {pe} 倍，高於近 10 年平均。");
  add("light.earn.growing", "Earnings momentum is strong.", "獲利動能強勁。");
  add("light.earn.flat", "Earnings are still growing at a moderate pace.", "獲利仍在溫和成長。");
  add("light.earn.weakening", "Earnings momentum is weakening — historically this came before more frequent large drawdowns.", "獲利動能正在轉弱；歷史上這種情況之後較常出現大跌。");
  add("light.backdrop", "These describe the backdrop; the site's tests show valuation and Capex do not time crashes.", "以上是背景資訊；網站的檢驗顯示，估值與資本支出無法用來預測崩盤時點。");
  add("light.disclaimer", "A risk reminder, not a buy or sell signal. The site cannot predict when a crash happens.", "這是風險提醒，不是買賣建議；網站無法預測何時崩盤。");
  add("light.rule", "How the light works: green when tomorrow's forecast volatility is below the historical median, yellow between the 50th and 80th percentile, red at or above the 80th percentile. Updated after every US trading day from {d} data.",
    "燈號規則：明日預估波動低於歷史中位數為綠燈，介於第 50 到第 80 百分位為黃燈，達第 80 百分位以上為紅燈。每個美股交易日收盤後自動更新，本次依 {d} 的資料。");
  add("light.more", "Details on the <a href='risk.html'>Risk</a> page.", "詳細數字請見<a href='risk.html'>風險頁</a>。");

  // ------------------------------------------------------------ index
  add("index.title", "Tech Cycle Backtest", "科技週期回測");
  add("index.asof", "Lag-1 regime strategy · nested walk-forward · as of <strong>{asof}</strong> · regime: <strong>{regime}</strong>",
    "落後一期的市場狀態策略 · 巢狀 walk-forward · 資料時間 <strong>{asof}</strong> · 狀態：<strong>{regime}</strong>");
  add("index.card.regime", "Official regime", "正式市場狀態");
  add("index.card.weight", "Risk weight in force", "目前持有的風險權重");
  add("index.card.prov", "Month-to-date (provisional)", "本月至今（暫定）");
  add("index.card.v3", "v3 candidate weight", "v3 候選模型權重");
  add("index.card.vol", "Next-month vol forecast", "下月波動預測");
  add("index.sub.monthEnd", "month-end {date}", "月底 {date}");
  add("index.sub.pe", " · P/E {pe}x", " · 本益比 {pe} 倍");
  add("index.sub.heldThrough", "held through {m}", "持有至 {m}");
  add("index.sub.prov", "{m} · data through {d} · next-month weight {w}", "{m} · 資料截至 {d} · 下月權重 {w}");
  add("index.sub.noProv", "no month in progress", "目前沒有進行中的月份");
  add("index.sub.v3", "{state} · vol {vol} → scale {scale} · tilt {tilt}", "{state} · 波動 {vol} → 縮放 {scale} · 加減碼 {tilt}");
  add("index.sub.v3mtd", " · MTD {w}", " · 本月至今 {w}");
  add("index.sub.vol", "90% {lo}–{hi}", "90% 區間 {lo}–{hi}");
  add("index.sub.volBase", " · P(DD&gt;20%, 12m): base rate {p} (model not skillful)", " · 12 個月內跌逾 20% 機率：歷史平均 {p}（模型無效）");
  add("index.sub.volModel", " · P(DD&gt;20%, 12m) {p}", " · 12 個月內跌逾 20% 機率 {p}");
  add("index.sub.var", " · 1-day 95% VaR {v}", " · 1 日 95% 風險值 {v}");
  add("index.sub.riskLink", " · <a href='risk.html'>Risk</a>", " · <a href='risk.html'>風險頁</a>");
  add("index.basis", "Headline metrics are <strong>out-of-sample</strong>: parameters re-chosen every January using only prior data (nested walk-forward).",
    "以下主要指標皆為<strong>樣本外</strong>結果：每年 1 月只用當時以前的資料重新選參數（巢狀 walk-forward）。");
  add("index.m.sharpe", "OOS Sharpe", "樣本外夏普比率");
  add("index.m.mdd", "OOS Max DD", "樣本外最大回撤");
  add("index.m.cagr", "OOS CAGR", "樣本外年化報酬");
  add("index.m.nav", "OOS Final NAV", "樣本外期末淨值");
  add("index.m.sharpeSub", "B&H {bh} · in-sample {is}", "買進持有 {bh} · 樣本內 {is}");
  add("index.m.bh", "B&H {v}", "買進持有 {v}");
  add("index.m.vol", "vol {v}", "波動 {v}");
  add("index.nav.h2", "NAV — v2 walk-forward (live) vs v3 candidate vs buy &amp; hold vs in-sample (hindsight)",
    "淨值 — v2 walk-forward（上線）vs v3 候選 vs 買進持有 vs 樣本內（事後諸葛）");
  add("index.nav.note", "The dashed \"in-sample\" line uses parameters picked with knowledge of the whole sample; the gap to the walk-forward line is the cost of hindsight. The v3 candidate is also walk-forward, but its design was chosen on 2026-11-23 after seeing full-sample studies — see Validation.",
    "虛線「樣本內」是用整段歷史挑出的參數，它與 walk-forward 線的差距，就是「事後諸葛」造成的高估。v3 候選同樣是 walk-forward，但它的設計是在 2026-11-23 看過全樣本研究後才決定的，詳見驗證頁。");
  add("index.nav.v2", "Walk-forward strategy (OOS)", "Walk-forward 策略（樣本外）");
  add("index.nav.bh", "Buy & hold", "買進持有");
  add("index.nav.is", "In-sample tuned (hindsight)", "樣本內調參（事後諸葛）");
  add("index.nav.v3", "v3 candidate (walk-forward)", "v3 候選（walk-forward）");
  add("index.nav.axis", "NAV (log)", "淨值（對數）");
  add("index.regime.h2", "Regime timeline (walk-forward)", "市場狀態時間軸（walk-forward）");
  add("index.regime.title", "Regime over time", "各時期的市場狀態");
  add("index.aux.h2", "Signals · VIX, overheat score, earnings momentum, executed weight", "訊號 · VIX、過熱分數、獲利動能、實際權重");
  add("index.aux.vix", "VIX (monthly mean)", "VIX（月平均）");
  add("index.aux.oh", "Overheat score", "過熱分數");
  add("index.aux.earn", "Earnings momentum score", "獲利動能分數");
  add("index.aux.w", "Executed risk weight", "實際風險權重");
  add("index.aux.score", "Score (z)", "分數（z）");
  add("index.pe.h2", "Valuation — aggregate mega-cap trailing P/E (market cap / TTM net income, point-in-time)",
    "估值 — 大型科技股合計本益比（總市值 ÷ 近四季淨利，以當時可得資料計算）");
  add("index.pe.note", "Σ market cap ÷ Σ TTM net income across names with positive earnings, chain-linked. Share counts from SEC filings, scaled for splits after each filing date. Before firm-level data exists the overheat score uses a price-extension proxy.",
    "以獲利為正的公司計算 Σ 市值 ÷ Σ 近四季淨利，並做連鎖銜接。股數取自 SEC 申報，並依申報日之後的分割調整。在有公司層級資料之前，過熱分數改用「股價偏離均線」作為替代指標。");
  add("index.pe.series", "Aggregate trailing P/E", "合計本益比");
  add("index.pe.axis", "P/E (x)", "本益比（倍）");
  add("index.capex.h2", "Capex intensity — mega-cap TTM Capex / revenue (SEC XBRL, point-in-time)",
    "資本支出強度 — 大型科技股近四季 Capex ÷ 營收（SEC XBRL，以當時可得資料計算）");
  add("index.capex.series", "TTM Capex / revenue (chain-linked)", "近四季 Capex ÷ 營收（連鎖銜接）");
  add("index.sc.h2", "Scenarios preview", "情境預覽");
  add("index.sc.note", "Rule-based trigger distances from the live parameters. <a href=\"scenarios.html\">Open full Scenarios view</a>",
    "依目前參數計算的觸發距離（規則式，非預測）。<a href=\"scenarios.html\">開啟完整情境頁</a>");
  add("index.sc.weight", "Risk weight:", "風險權重：");
  add("index.footer", "Source: {src} · {from} → {to} · {n} OOS months · engine {ver}", "資料來源：Yahoo（XLK/^NDX/^VIX）、FRED、SEC XBRL · {from} → {to} · 樣本外 {n} 個月 · 引擎 {ver}");

  // --------------------------------------------------------- scenarios
  add("sc.title", "Tech Cycle — Scenarios", "科技週期 — 情境");
  add("sc.asof", "Rule-based risk brief · lag-1 engine · not trade signals · as of <strong>{asof}</strong>",
    "規則式風險摘要 · 落後一期引擎 · 非交易訊號 · 資料時間 <strong>{asof}</strong>");
  add("sc.card.regime", "Official regime", "正式市場狀態");
  add("sc.card.weight", "Weight in force", "目前權重");
  add("sc.card.prov", "Month-to-date", "本月至今");
  add("sc.card.fit", "Params fit for", "參數適用年度");
  add("sc.card.fitSub", "walk-forward, data through prior Dec", "walk-forward，使用至前一年 12 月的資料");
  add("sc.sub.dataThrough", "data through {d}", "資料截至 {d}");
  add("sc.trig.h2", "Trigger distances (provisional signals if a month is in progress)", "觸發距離（若月份進行中，使用暫定訊號）");
  add("sc.trig.cols", "Trigger|Signal|Value|Threshold|Fires when|Distance|Status|Weight if active", "觸發條件|訊號|目前值|門檻|觸發方向|距離|狀態|觸發時權重");
  add("sc.trig.above", "above", "高於門檻");
  add("sc.trig.below", "below", "低於門檻");
  add("sc.sig.shock", "VIX (monthly mean)", "VIX（月平均）");
  add("sc.sig.overheat", "Overheat score", "過熱分數");
  add("sc.sig.digestion", "Earnings momentum score", "獲利動能分數");
  add("sc.h2", "Scenarios", "情境");
  add("sc.id.base", "base", "基準");
  add("sc.id.overheat", "overheat", "過熱");
  add("sc.id.shock", "shock", "衝擊");
  add("sc.id.digestion", "digestion", "消化");
  add("sc.horizon", "1-3 months", "1–3 個月");
  add("sc.base.thesis", "Signals stay on their current side of every threshold; regime remains {regime}.", "各訊號維持在門檻的同一側，市場狀態維持「{regime}」。");
  add("sc.base.flip.vix", "VIX {v} vs Shock threshold {t}", "VIX {v}，衝擊門檻 {t}");
  add("sc.base.flip.oh", "Overheat {v} vs threshold {t}", "過熱分數 {v}，門檻 {t}");
  add("sc.base.flip.earn", "Earnings score {v} vs Digestion threshold {t}", "獲利分數 {v}，消化門檻 {t}");
  add("sc.base.rationale", "Engine weight implied by the latest (provisional if in-progress) signals.", "依最新訊號（月份進行中則為暫定訊號）推得的引擎權重。");
  add("sc.oh.active", "Overheat trigger already active (score {v} > {t}); it binds whenever Shock is not active.", "過熱條件已觸發（分數 {v} > {t}）；只要衝擊未觸發，就會生效。");
  add("sc.oh.thesis", "Valuation extension + Capex intensity lift the overheat score by {d} to cross {t} while VIX stays below {vt}.",
    "若估值與資本支出強度使過熱分數再上升 {d}、超過 {t}，且 VIX 維持在 {vt} 以下。");
  add("sc.oh.flip1", "Overheat score > threshold", "過熱分數 > 門檻");
  add("sc.oh.flip2", "Shock not active (Shock has priority)", "衝擊未觸發（衝擊優先）");
  add("sc.oh.rationale", "Overheat defense weight, applied the month after the signal.", "過熱防禦權重，於訊號出現的下個月執行。");
  add("sc.shock.active", "Shock trigger already active (monthly-average VIX {v} > {t}); Shock overrides every other regime.", "衝擊條件已觸發（VIX 月平均 {v} > {t}）；衝擊優先於所有其他狀態。");
  add("sc.shock.thesis", "Monthly-average VIX rises {d} points to exceed {t}; Shock overrides every other regime.", "若 VIX 月平均再上升 {d} 點、超過 {t}；衝擊優先於所有其他狀態。");
  add("sc.shock.flip1", "Monthly mean VIX > threshold", "VIX 月平均 > 門檻");
  add("sc.shock.rationale", "Shock defense weight (max de-risking).", "衝擊防禦權重（最大幅度降低風險）。");
  add("sc.dig.active", "Digestion trigger already active (earnings score {v} < {t}).", "消化條件已觸發（獲利分數 {v} < {t}）。");
  add("sc.dig.thesis", "Aggregate TTM earnings momentum drops {d} std units to below {t} (Capex digestion / earnings downgrade cycle).",
    "若合計近四季獲利動能再下降 {d} 個標準差、低於 {t}（資本支出消化／獲利下修期）。");
  add("sc.dig.flip1", "Earnings score < threshold", "獲利分數 < 門檻");
  add("sc.dig.flip2", "Neither Shock nor Overheat active", "衝擊與過熱皆未觸發");
  add("sc.dig.rationale", "Digestion defense weight.", "消化防禦權重。");
  add("sc.weight", "Risk weight:", "風險權重：");
  add("sc.interp.official", "Official regime at {date} month-end: {regime} (risk weight {w} held through {m}). ", "{date} 月底的正式狀態：{regime}（風險權重 {w}，持有至 {m}）。");
  add("sc.interp.prov", "Month-to-date ({m}, data through {d}) signals point to {regime}; if the month ended today next month's weight would be {w}. ",
    "本月至今（{m}，資料截至 {d}）的訊號指向「{regime}」；若本月今天結束，下月權重將為 {w}。");
  add("sc.interp.tail", "Parameters were chosen by walk-forward using data through Dec {y} only. These are rule-based trigger distances, not return forecasts.",
    "參數由 walk-forward 只用到 {y} 年 12 月的資料選出。以下是規則式的觸發距離，不是報酬預測。");
  add("sc.footer", "Snapshot: rule-based brief · as_of {asof} · DATA_SOURCE={src}", "快照：規則式摘要 · 資料時間 {asof} · 資料來源 {src}");

  // --------------------------------------------------------- validation
  add("val.title", "Tech Cycle — Validation", "科技週期 — 驗證");
  add("val.asof", "Nested walk-forward · as of <strong>{asof}</strong>", "巢狀 walk-forward · 資料時間 <strong>{asof}</strong>");
  add("val.models.h2", "Model comparison — v2 regime (live) vs v3 tilt + vol target (candidate)", "模型比較 — v2 市場狀態模型（上線）vs v3 加減碼＋波動目標（候選）");
  add("val.models.col0", "Model (OOS {a} → {b})", "模型（樣本外 {a} → {b}）");
  add("val.cols.metrics", "Sharpe|CAGR|Vol|Max DD|Calmar|Final NAV|Avg weight", "夏普|年化報酬|波動|最大回撤|Calmar|期末淨值|平均權重");
  add("val.model.regime_v2", "v2 regime (live)", "v2 市場狀態模型（上線）");
  add("val.model.tilt_v3", "v3 tilt + vol target (candidate)", "v3 加減碼＋波動目標（候選）");
  add("val.model.buy_hold", "Buy & hold", "買進持有");
  add("val.model.vol_matched_bh_v3", "Vol-matched B&H (to v3, ex-post)", "同波動買進持有（對齊 v3，事後）");
  add("val.design.none", "v3 was designed on {d} after seeing the full-sample signal study, so its walk-forward numbers above are still optimistic. Only months after the design date are a clean test: none yet.",
    "v3 是在 {d} 看過全樣本訊號研究後才設計的，所以上方的 walk-forward 數字仍偏樂觀。只有設計日之後的月份才是乾淨的檢驗：目前尚無資料。");
  add("val.design.some", "v3 was designed on {d} after seeing the full-sample signal study, so its walk-forward numbers above are still optimistic. Only months after the design date are a clean test: {n} month(s) so far, v3 {v3} vs B&H {bh}.",
    "v3 是在 {d} 看過全樣本訊號研究後才設計的，所以上方的 walk-forward 數字仍偏樂觀。只有設計日之後的月份才是乾淨的檢驗：目前 {n} 個月，v3 {v3}，買進持有 {bh}。");
  add("val.promo.h2", "v3 promotion rule — pre-registered", "v3 切換規則 — 事先登錄");
  add("val.promo.doc", "docs/model-promotion.md", "docs/model-promotion.md（英文）");
  add("val.promo.cols", "#|Criterion|Status|Detail", "#|標準|狀態|細節");
  add("val.promo.note", "Status is computed daily and reported only. The engine never switches the live model; the owner decides.", "狀態每天計算並僅供參考。引擎不會自動切換上線模型，由擁有者決定。");
  add("val.promo.state", "<strong>State: {state}.</strong> {note} Evaluation window starts {first}; earliest decision after {earliest}; retire if still failing after {retire}.",
    "<strong>狀態：{state}。</strong>{note} 評估期間自 {first} 起；最早可於 {earliest} 之後決定；若到 {retire} 仍未達標則淘汰。");
  add("promo.state.collecting", "collecting", "收集中");
  add("promo.state.eligible", "eligible", "可切換");
  add("promo.state.not_met", "not met", "未達標");
  add("promo.state.retire", "retire", "淘汰");
  add("promo.state.invalid", "invalid", "無效");
  add("promo.note.collecting", "Collecting post-design evidence: {n}/{min} months. No decision before {earliest}.", "累積設計日後的證據中：{n}/{min} 個月。{earliest} 之前不做決定。");
  add("promo.note.eligible", "All criteria met. Promotion is eligible; the owner decides. The engine does not switch automatically.", "所有標準皆達成，可以切換；由擁有者決定，引擎不會自動切換。");
  add("promo.note.not_met", "Minimum period reached but criteria not met; keep collecting until {retire}.", "已達最短期間但標準未達成；繼續收集至 {retire}。");
  add("promo.note.retire", "Criteria still not met after {r} months: retire the v3 candidate (or re-design with a new design date).", "滿 {r} 個月仍未達標：淘汰 v3 候選（或以新的設計日重新設計）。");
  add("promo.note.invalid", "v3 specification changed after the design date: the evaluation clock must be reset.", "v3 規格在設計日後被修改：評估期間必須重新計算。");
  add("promo.C1", "At least {min} post-design months", "設計日後至少 {min} 個月");
  add("promo.C2", "v3 Sharpe > vol-matched B&H Sharpe (post-design)", "設計日後 v3 夏普 > 同波動買進持有");
  add("promo.C3", "v3 Max DD no worse than vol-matched B&H by > {tol}", "v3 最大回撤不比同波動買進持有差超過 {tol}");
  add("promo.C4", "Full OOS history (2000+): v3 Sharpe >= B&H Sharpe", "完整樣本外期間（2000 起）：v3 夏普 ≥ 買進持有");
  add("promo.C5", "v3 specification unchanged since design date", "設計日後 v3 規格未變更");
  add("promo.C6", "No gap > {d} days between successful daily refreshes", "成功的每日更新間隔不超過 {d} 天");
  add("promo.d.needs2", "needs >= 2 months", "需至少 2 個月");
  add("promo.d.fpOk", "fingerprint matches", "指紋相符");
  add("promo.d.fpChanged", "changed: reset design date", "已變更：需重設設計日");
  add("promo.d.gap", "longest gap {n} d", "最長間隔 {n} 天");
  add("promo.d.noHistory", "no history", "尚無紀錄");
  add("val.pick.label", "Details for:", "詳細資料：");
  add("val.pick.v2", "v2 regime (live)", "v2 市場狀態（上線）");
  add("val.pick.v3", "v3 candidate", "v3 候選");
  add("val.summary", "<strong>{model}.</strong> <strong>Out-of-sample window:</strong> {a} → {b} ({n} months). <strong>Search space:</strong> {grid} configurations. <strong>Objective:</strong> Sharpe − {pen} × max(0, Max DD beyond {budget}). <strong>Refit:</strong> every 12 months (January), expanding window, training from {train}.<br/><br/>{verdict}",
    "<strong>{model}。</strong><strong>樣本外期間：</strong>{a} → {b}（{n} 個月）。<strong>搜尋範圍：</strong>{grid} 組參數。<strong>目標函數：</strong>夏普 − {pen} × max(0, 最大回撤超過 {budget} 的部分)。<strong>重新估計：</strong>每 12 個月（1 月），擴張視窗，訓練資料自 {train} 起。<br/><br/>{verdict}");
  add("val.verdict.good", "The out-of-sample strategy matched or beat buy &amp; hold on Sharpe ({s} vs {bh}), at {v} vs {bv} volatility.",
    "樣本外策略的夏普比率持平或優於買進持有（{s} vs {bh}），波動為 {v} vs {bv}。");
  add("val.verdict.bad", "The out-of-sample strategy <strong>under-performed</strong> buy &amp; hold on Sharpe ({s} vs {bh}). The in-sample-tuned version looks far better ({is} full sample) — that gap is hindsight, not skill.",
    "樣本外策略的夏普比率<strong>不如</strong>買進持有（{s} vs {bh}）。樣本內調參的版本看起來好很多（全樣本 {is}），但這個差距來自事後諸葛，不是真本事。");
  add("val.model.label.regime_v2", "v2 regime model", "v2 市場狀態模型");
  add("val.model.label.tilt_v3", "v3 tilt + vol-target model", "v3 加減碼＋波動目標模型");
  add("val.cmp.h2", "Out-of-sample vs hindsight vs benchmarks", "樣本外 vs 事後諸葛 vs 基準");
  add("val.cmp.col0", "Track", "績效線");
  add("val.cmp.oos", "Walk-forward strategy (OOS)", "Walk-forward 策略（樣本外）");
  add("val.cmp.is", "In-sample best, same window (hindsight)", "樣本內最佳，同期間（事後諸葛）");
  add("val.cmp.bh", "Buy & hold", "買進持有");
  add("val.cmp.vm", "Vol-matched buy & hold (ex-post)", "同波動買進持有（事後）");
  add("val.stats.h2", "Multiple-testing statistics", "多重檢定統計");
  add("val.stats.dsr", "DSR (in-sample best)", "DSR（樣本內最佳）");
  add("val.stats.dsrSub", "{n} trials · SR₀ {sr} ann.", "{n} 次試驗 · SR₀ 年化 {sr}");
  add("val.stats.psr0", "PSR OOS vs 0", "PSR 樣本外 vs 0");
  add("val.stats.psr0Sub", "P(true Sharpe > 0)", "真實夏普 > 0 的機率");
  add("val.stats.psrbh", "PSR OOS vs B&H", "PSR 樣本外 vs 買進持有");
  add("val.stats.psrbhSub", "P(true Sharpe > B&H Sharpe)", "真實夏普 > 買進持有的機率");
  add("val.stats.note", "DSR = Deflated Sharpe Ratio (Bailey &amp; López de Prado): probability the in-sample best Sharpe is real after accounting for every configuration tried. PSR = Probabilistic Sharpe Ratio of the out-of-sample track record. Both assume roughly i.i.d. monthly returns.",
    "DSR（Deflated Sharpe Ratio，Bailey &amp; López de Prado）：考慮所有試過的參數組合後，樣本內最佳夏普為真的機率。PSR（Probabilistic Sharpe Ratio）：樣本外績效的夏普比率為真的機率。兩者都假設月報酬大致獨立同分配。");
  add("val.valin.h2", "Valuation input (v2 model) — aggregate P/E vs price-extension proxy", "估值輸入（v2 模型）— 合計本益比 vs 股價偏離替代指標");
  add("val.valin.cols", "Valuation input (v2 model)|OOS Sharpe|OOS Max DD|OOS Final NAV|Overheat months (OOS)|IC vs next 12m|IC window",
    "估值輸入（v2 模型）|樣本外夏普|樣本外最大回撤|樣本外期末淨值|過熱月數（樣本外）|與未來 12 個月報酬的 IC|IC 期間");
  add("val.valin.pe", "Aggregate P/E (default)", "合計本益比（預設）");
  add("val.valin.price_ext", "Price extension proxy (v2.0)", "股價偏離替代指標（v2.0）");
  add("val.valin.note", "IC = correlation of the valuation z-score with the next 12-month log return of the risk asset, over the window where firm-level P/E exists (negative = high valuation preceded weaker returns). Overlapping windows: descriptive only, not a significance test.",
    "IC：估值 z 分數與風險資產未來 12 個月對數報酬的相關係數，期間為有公司層級本益比的時段（負值代表高估值之後報酬較弱）。區間重疊，僅供描述，不是顯著性檢定。");
  add("val.abl.h2", "Ablation — each variant gets its own nested walk-forward", "拆除比較 — 每個版本各自做巢狀 walk-forward");
  add("val.abl.cols", "Variant|Sharpe|CAGR|Max DD|Calmar|Final NAV|Turnover/yr", "版本|夏普|年化報酬|最大回撤|Calmar|期末淨值|年週轉率");
  add("abl.full", "Full model (Shock + Overheat + Digestion)", "完整模型（衝擊＋過熱＋消化）");
  add("abl.no_shock", "Without Shock (VIX)", "拿掉衝擊（VIX）");
  add("abl.no_overheat", "Without Overheat (valuation + Capex)", "拿掉過熱（估值＋Capex）");
  add("abl.no_digestion", "Without Digestion (earnings)", "拿掉消化（獲利）");
  add("abl.shock_only", "Shock (VIX) only", "只有衝擊（VIX）");
  add("abl.tilt.full", "Full v3 (price-ext + P/E + Capex tilts, earnings cut, vol target)", "完整 v3（股價偏離＋本益比＋Capex 加減碼、獲利減碼、波動目標）");
  add("abl.no_vol_target", "Without vol targeting", "拿掉波動目標");
  add("abl.no_price_ext", "Without price-extension tilt", "拿掉股價偏離加減碼");
  add("abl.no_pe", "Without P/E tilt", "拿掉本益比加減碼");
  add("abl.no_capex", "Without Capex tilt", "拿掉 Capex 加減碼");
  add("abl.no_earnings", "Without earnings cut", "拿掉獲利減碼");
  add("abl.vol_target_only", "Vol targeting only", "只有波動目標");
  add("abl.buy_hold", "Buy & hold (XLK/NDX)", "買進持有（XLK/NDX）");
  add("abl.vol_matched_bh", "Vol-matched B&H ({c} risk / {k} cash, ex-post)", "同波動買進持有（{c} 風險資產／{k} 現金，事後）");
  add("val.sub.h2", "Crisis sub-periods (OOS strategy vs buy &amp; hold)", "危機期間（樣本外策略 vs 買進持有）");
  add("val.sub.cols", "Period|Window|Strategy return|Strategy MDD|B&H return|B&H MDD", "期間|起訖|策略報酬|策略最大回撤|買進持有報酬|買進持有最大回撤");
  add("period.DotCom 2000-2002", "DotCom 2000-2002", "網路泡沫 2000–2002");
  add("period.GFC 2008-2009", "GFC 2008-2009", "金融海嘯 2008–2009");
  add("period.COVID 2020", "COVID 2020", "新冠疫情 2020");
  add("period.Rate shock 2022", "Rate shock 2022", "升息衝擊 2022");
  add("period.AI Capex 2023+", "AI Capex 2023+", "AI 資本支出 2023+");
  add("val.sens.h2", "Parameter sensitivity — full-sample Sharpe", "參數敏感度 — 全樣本夏普");
  add("val.sens.note", "Rows: {y}; columns: {x}; other parameters fixed at the in-sample best {params}. A smooth plateau suggests robustness; an isolated peak suggests over-fitting.",
    "列：{y}；欄：{x}；其他參數固定在樣本內最佳值 {params}。平緩的高原代表穩健，孤立的尖峰代表過度擬合。");
  add("val.folds.h2", "Walk-forward folds — parameters chosen each January", "Walk-forward 各年度 — 每年 1 月選出的參數");
  add("val.folds.c0", "Test year", "測試年度");
  add("val.folds.c1", "Trained through", "訓練資料截至");
  add("val.folds.trainSharpe", "Train Sharpe", "訓練期夏普");
  add("val.folds.testReturn", "Test return", "測試期報酬");
  add("val.folds.live", "live", "進行中");
  add("param.vix_threshold", "VIX thr", "VIX 門檻");
  add("param.overheat_threshold", "OH thr", "過熱門檻");
  add("param.earn_threshold", "Earn thr", "獲利門檻");
  add("param.w_overheat", "w OH", "過熱權重");
  add("param.w_shock", "w Shock", "衝擊權重");
  add("param.w_digestion", "w Dig", "消化權重");
  add("param.c_px", "c PxExt", "股價偏離係數");
  add("param.c_pe", "c P/E", "本益比係數");
  add("param.c_capex", "c Capex", "Capex 係數");
  add("param.base", "Base", "基礎權重");
  add("param.earn_cut", "Earn cut", "獲利減碼");
  add("param.vol_input", "Vol input", "波動來源");
  add("param.vol_target", "Vol target", "波動目標");
  add("val.dq.h2", "Data quality &amp; provenance (latest run)", "資料品質與來源（最近一次執行）");
  add("val.dq.cols", "Check|Status|Detail", "檢查項目|狀態|細節（原文）");
  add("val.src.cols", "Source|Latest observation / filing", "資料來源|最新資料日／申報日");
  add("val.footer", "engine {ver}{sha} · raw inputs hashed in data/health.json (raw_manifest)", "引擎 {ver}{sha} · 原始資料雜湊記錄於 data/health.json（raw_manifest）");
  add("dq.market_freshness", "market_freshness", "市場資料新鮮度");
  add("dq.vix_freshness", "vix_freshness", "VIX 新鮮度");
  add("dq.no_missing_signals", "no_missing_signals", "訊號無缺值");
  add("dq.return_range", "return_range", "報酬範圍");
  add("dq.vix_range", "vix_range", "VIX 範圍");
  add("dq.panel_length", "panel_length", "資料長度");
  add("dq.sec_coverage", "sec_coverage", "SEC 涵蓋家數");
  add("dq.sec_freshness", "sec_freshness", "SEC 新鮮度");
  add("dq.pe_coverage", "pe_coverage", "本益比涵蓋家數");
  add("dq.pe_range", "pe_range", "本益比範圍");
  add("dq.epu_freshness", "epu_freshness", "EPU 新鮮度");
  add("dq.capex_source_current", "capex_source_current", "Capex 資料來源");
  add("dq.fetch_warning", "fetch_warning", "下載警告");

  // ------------------------------------------------------- cross-market
  add("xm.h2", "Out-of-domain test — frozen v3 design on 9 other markets (pre-registered)", "換市場驗證 — 凍結的 v3 設計套用到 9 個其他市場（事先登錄）");
  add("xm.verdict.fail", "<strong>Result: FAILED.</strong> The unchanged v3 design beat buy &amp; hold on Sharpe in {n}/{m} markets; the average Sharpe difference is {d} (90% CI {lo} to {hi}). Its edge on tech does not generalize, which strengthens the view that the tech result was partly luck or hindsight. Criteria were fixed on {reg} before any real-data run.",
    "<strong>結果：未通過。</strong>完全不改的 v3 設計，只在 {n}/{m} 個市場的夏普比率勝過買進持有；平均夏普差距 {d}（90% 信賴區間 {lo} 至 {hi}）。它在科技股上的優勢無法推廣到其他市場，代表科技股的結果有一部分來自運氣或事後諸葛。成功標準在 {reg} 跑任何真實資料之前就已定好。");
  add("xm.verdict.pass", "<strong>Result: PASSED.</strong> The unchanged v3 design beat buy &amp; hold on Sharpe in {n}/{m} markets; average Sharpe difference {d} (90% CI {lo} to {hi}). Criteria were fixed on {reg} before any real-data run.",
    "<strong>結果：通過。</strong>完全不改的 v3 設計在 {n}/{m} 個市場的夏普比率勝過買進持有；平均夏普差距 {d}（90% 信賴區間 {lo} 至 {hi}）。成功標準在 {reg} 跑任何真實資料之前就已定好。");
  add("xm.crit.cols", "#|Criterion|Status|Result", "#|標準|狀態|結果");
  add("xm.C1", "v3 Sharpe > vol-matched buy & hold in ≥ {k} of 9 markets", "至少 {k}/9 個市場 v3 夏普 > 同波動買進持有");
  add("xm.C2", "Mean Sharpe difference > 0 with 90% joint-bootstrap CI excluding 0", "平均夏普差距 > 0，且 90% 聯合 bootstrap 信賴區間不含 0");
  add("xm.C3", "(secondary) v3 Max DD smaller in ≥ {k} of 9 markets", "（次要）至少 {k}/9 個市場 v3 最大回撤較小");
  add("xm.d.C1", "{n}/{m} markets", "{n}/{m} 個市場");
  add("xm.d.C2", "mean {d}, CI [{lo}, {hi}]", "平均 {d}，信賴區間 [{lo}, {hi}]");
  add("xm.cols", "Market|OOS window|v3 Sharpe|B&H Sharpe|Difference|v3 Max DD|Vol-matched Max DD|v3 CAGR|B&H CAGR|Avg weight",
    "市場|樣本外期間|v3 夏普|買進持有夏普|差距|v3 最大回撤|同波動最大回撤|v3 年化報酬|買進持有年化|平均權重");
  add("xm.note", "Same 1,080-configuration grid and walk-forward as on tech; price-extension and volatility signals use each market's own prices; tech fundamentals (P/E, Capex, earnings) only for ^SOX. Vol-matched buy & hold has the same Sharpe as buy & hold. Most windows start 2010–2012 (ETF listing + 7-year warm-up) and contain few crises, where v3's insurance-like profile helps most; that context does not change the pre-set verdict.",
    "與科技股相同的 1,080 組參數與 walk-forward；股價偏離與波動訊號用各市場自己的價格；科技基本面（本益比、Capex、獲利）只用於 ^SOX。同波動買進持有的夏普與買進持有相同。多數市場的樣本外期間從 2010–2012 年開始（ETF 上市晚加上 7 年暖身），期間大型危機不多，而 v3 這種「保險型」策略主要在危機時才有優勢；但這個背景不改變事先定好的判定。");
  add("mkt.^SOX", "Semiconductors (^SOX)", "半導體（^SOX）");
  add("mkt.SPY", "US large caps (SPY)", "美國大型股（SPY）");
  add("mkt.XLF", "US financials (XLF)", "美國金融（XLF）");
  add("mkt.XLE", "US energy (XLE)", "美國能源（XLE）");
  add("mkt.XLV", "US health care (XLV)", "美國醫療（XLV）");
  add("mkt.EWJ", "Japan (EWJ)", "日本（EWJ）");
  add("mkt.EWG", "Germany (EWG)", "德國（EWG）");
  add("mkt.EWU", "United Kingdom (EWU)", "英國（EWU）");
  add("mkt.EEM", "Emerging markets (EEM)", "新興市場（EEM）");

  // ------------------------------------------------------------ signals
  add("sig.title", "Tech Cycle — Signals", "科技週期 — 訊號");
  add("sig.asof", "Stand-alone signal tests · as of <strong>{asof}</strong>", "單一訊號檢驗 · 資料時間 <strong>{asof}</strong>");
  add("sig.summary", "Each signal is tested on its own, outside the regime rules: does a high (or low) reading precede weaker returns or more frequent large drawdowns of the risk asset? Window {a} → {b} (12-month targets). Unconditional: next-12m excess log return {r}, probability of a drawdown worse than {cut} {p}.<br/><br/><strong>Overheat score:</strong> {rv}; {dv}.",
    "每個訊號都在市場狀態規則之外單獨檢驗：訊號偏高（或偏低）之後，風險資產的報酬是否較差、大跌是否較頻繁？期間 {a} → {b}（以未來 12 個月為目標）。無條件基準：未來 12 個月超額對數報酬 {r}，回撤超過 {cut} 的機率 {p}。<br/><br/><strong>過熱分數：</strong>{rv}；{dv}。");
  add("sig.verdict.h2", "Does each signal justify de-risking? (top vs bottom quintile, next 12 months)", "各訊號是否支持減碼？（最高 vs 最低五分位，未來 12 個月）");
  add("sig.verdict.cols", "Signal|De-risk side|Return Q5−Q1 (pp)|90% CI|Returns|P(DD) Q5−Q1 (pp)|90% CI|Drawdowns",
    "訊號|減碼方向|報酬 Q5−Q1（百分點）|90% 信賴區間|報酬判讀|大跌機率 Q5−Q1（百分點）|90% 信賴區間|回撤判讀");
  add("sig.verdict.note", "Quintiles are point-in-time (each month ranked against its own history only). Spread = top-quintile minus bottom-quintile mean; 90% CI from a 12-month moving-block bootstrap. \"De-risk side\" is where the regime engine cuts risk (Digestion fires on LOW earnings momentum). <strong>supports</strong> = the de-risk side preceded lower returns / more drawdowns with a CI excluding zero; <strong>contradicts</strong> = the opposite; hover a tag for the full reading.",
    "五分位以當時可得資料計算（每個月只跟自己的歷史比較）。差距＝最高五分位平均減最低五分位平均；90% 信賴區間以 12 個月區塊 bootstrap 估計。「減碼方向」是引擎降低風險的那一側（消化是在獲利動能「低」時觸發）。<strong>支持</strong>＝減碼那一側之後報酬較低／大跌較多，且信賴區間不含 0；<strong>相反</strong>＝結果相反；滑鼠移到標籤上可看完整說明。");
  add("side.high", "high", "高");
  add("side.low", "low", "低");
  add("sig.v.ret.supports", "{side} signal preceded LOWER returns", "訊號{side}時，之後報酬較低");
  add("sig.v.ret.contradicts", "{side} signal preceded HIGHER returns", "訊號{side}時，之後報酬反而較高");
  add("sig.v.risk.supports", "{side} signal preceded MORE large drawdowns", "訊號{side}時，之後大跌較多");
  add("sig.v.risk.contradicts", "{side} signal preceded FEWER large drawdowns", "訊號{side}時，之後大跌反而較少");
  add("sig.v.inconclusive", "inconclusive (CI spans 0)", "不確定（信賴區間跨 0）");
  add("sig.v.prefix.supports", "supports de-risking", "支持減碼");
  add("sig.v.prefix.contradicts", "contradicts de-risking", "與減碼假設相反");
  add("sig.name.overheat_score", "Overheat score ((val_z + capex_z) / 2)", "過熱分數（(估值 z + Capex z) / 2）");
  add("sig.name.val_z", "Valuation z (P/E from 2013, price extension before)", "估值 z（2013 起為本益比，之前為股價偏離）");
  add("sig.name.capex_z", "Capex intensity z", "資本支出強度 z");
  add("sig.name.earn_score", "Earnings momentum score", "獲利動能分數");
  add("sig.name.vix", "VIX (monthly mean)", "VIX（月平均）");
  add("sig.q.h2", "Quintile profile", "五分位分布");
  add("sig.q.pick", "Signal", "訊號");
  add("sig.q.ret", "Mean next-12m excess log return", "未來 12 個月平均超額對數報酬");
  add("sig.q.dd", "P(drawdown < {cut})", "回撤超過 {cut} 的機率");
  add("sig.q.low", " (low)", "（低）");
  add("sig.q.high", " (high)", "（高）");
  add("sig.q.ret.axis", "Return", "報酬");
  add("sig.q.dd.axis", "Drawdown probability", "大跌機率");
  add("sig.sc.h2", "Overheat score vs next-12-month excess return", "過熱分數 vs 未來 12 個月超額報酬");
  add("sig.sc.note", "Each dot is a month-end. Points are colored by era because the score is spliced: macro proxies before 2013, SEC firm-level data after.",
    "每個點是一個月底。依時期上色，因為分數是銜接而成：2013 年前用總體替代指標，之後用 SEC 公司層級資料。");
  add("sig.sc.early", "1993–2012 (macro proxies)", "1993–2012（總體替代指標）");
  add("sig.sc.late", "2013+ (SEC firm-level)", "2013+（SEC 公司層級）");
  add("sig.sc.x", "Overheat score at month-end", "月底過熱分數");
  add("sig.sc.y", "Next-12m excess log return", "未來 12 個月超額對數報酬");
  add("sig.sc.tip", "{d}: score {x}, next 12m {y}", "{d}：分數 {x}，未來 12 個月 {y}");
  add("sig.ic.h2", "Information coefficient by horizon (Spearman IC · Newey-West t)", "各期間資訊係數（Spearman IC · Newey-West t 值）");
  add("sig.ic.col0", "Signal", "訊號");
  add("sig.ic.col", "{h}m IC (t)", "{h} 個月 IC（t）");
  add("sig.ic.note", "Forward windows overlap, so ordinary t-stats are inflated; Newey-West uses lag h−1. |t| &lt; 2 should be read as noise.",
    "未來報酬的區間彼此重疊，一般 t 值會被高估；Newey-West 使用 h−1 期落後。|t| &lt; 2 應視為雜訊。");
  add("sig.era.h2", "Stability across eras (12-month IC)", "跨時期穩定性（12 個月 IC）");
  add("sig.era.col", "{era} IC (t)", "{era} IC（t）");
  add("era.1993-2012 (macro proxies)", "1993-2012 (macro proxies)", "1993–2012（總體替代指標）");
  add("era.2013+ (SEC firm-level)", "2013+ (SEC firm-level)", "2013+（SEC 公司層級）");
  add("sig.thr.h2", "Overheat thresholds used by the strategy grid", "策略參數網格使用的過熱門檻");
  add("sig.thr.cols", "Overheat >|Months above|Share|Next-12m ret. above|below|P(dd) above|below",
    "過熱 >|高於門檻月數|比例|高於時未來 12 個月報酬|低於時|高於時大跌機率|低於時");
  add("sig.footer", "Settings: Newey-West, lag h-1 · moving block, 12m blocks, 1000 reps, 90% CI · buckets need {n} months of history · engine {ver}",
    "設定：Newey-West（落後 h−1）· 12 個月區塊 bootstrap，1000 次，90% 信賴區間 · 分組需至少 {n} 個月歷史 · 引擎 {ver}");

  // --------------------------------------------------------------- risk
  add("risk.title", "Tech Cycle — Risk", "科技週期 — 風險");
  add("risk.asof", "Risk estimates · walk-forward, out-of-sample · as of <strong>{asof}</strong>", "風險估計 · walk-forward 樣本外 · 資料時間 <strong>{asof}</strong>");
  add("risk.summary", "<strong>What this page can and cannot tell you.</strong> Next-month <em>volatility</em> is forecastable out-of-sample (R² {r2} vs the historical mean). The probability of a large <em>drawdown event</em> is not: the walk-forward model {beats} the historical base rate. Large drawdowns since 2008 came in only two episodes, both starting from calm markets, so there is too little to learn from. {tail}",
    "<strong>這一頁能告訴你什麼、不能告訴你什麼。</strong>下個月的<em>波動大小</em>可以預測（樣本外 R² {r2}，相對於歷史平均）。<em>大跌事件</em>的機率則不行：walk-forward 模型{beats}歷史平均。2008 年後的大跌只有兩次，而且都從平靜的市場開始，可學習的樣本太少。{tail}");
  add("risk.beats.yes", "beats", "勝過");
  add("risk.beats.no", "does <strong>not</strong> beat", "<strong>沒有</strong>勝過");
  add("risk.summary.tail", "The headline probability below is therefore the base rate; the model value is shown for reference only.", "因此下方的主要機率顯示歷史平均，模型數值僅供參考。");
  add("risk.st.h2", "Short-term risk — next trading day / next 5 days (daily HAR model)", "短期風險 — 下一個交易日／未來 5 日（每日 HAR 模型）");
  add("risk.st.var", "1-day 95% VaR", "1 日 95% 風險值（VaR）");
  add("risk.st.varSub", "1-in-20 trading days a loss larger than this is expected · from close {d} · {m}", "約每 20 個交易日會有 1 天虧損超過此值 · 自 {d} 收盤起算 · {m}");
  add("risk.st.vol1", "Next-day volatility (annualized)", "明日波動（年化）");
  add("risk.st.vol1Sub", "≈ {d} daily move (1 sd) · EWMA {e}", "約當單日 ±{d}（1 個標準差）· EWMA {e}");
  add("risk.st.vol5", "Next 5 days volatility", "未來 5 日波動");
  add("risk.st.vol5Sub", "1 sd over 5 days · {a} annualized", "5 日 1 個標準差 · 年化 {a}");
  add("risk.st.ret", "Next-day return", "隔日報酬");
  add("risk.st.varLine", "−95% VaR (forecast at prior close)", "−95% VaR（前一日收盤時的預測）");
  add("risk.st.varNote", "Last 3 years, out-of-sample. Red bars are breaches (loss beyond the VaR set the evening before). Live model breached on {r} of days since 2000 (target 5%).",
    "最近 3 年，樣本外。紅色長條代表「突破」（虧損超過前一晚設定的 VaR）。上線模型自 2000 年起有 {r} 的交易日突破（目標 5%）。");
  add("risk.st.acc.h2", "Out-of-sample forecast accuracy (QLIKE, lower is better)", "樣本外預測準確度（QLIKE，越低越好）");
  add("risk.st.acc.cols", "Horizon|Model|QLIKE|Vol correlation|Days", "期間|模型|QLIKE|波動相關係數|天數");
  add("risk.st.dm.cols", "Horizon|Comparison|QLIKE improvement|Diebold-Mariano t|Reading", "期間|比較|QLIKE 改善|Diebold-Mariano t 值|判讀");
  add("risk.st.bt.h2", "95% VaR backtest (target breach rate 5%)", "95% VaR 回測（目標突破率 5%）");
  add("risk.st.bt.cols", "Model|Breaches|Rate|Kupiec p (coverage)|Christoffersen p (independence)|Avg VaR", "模型|突破次數|突破率|Kupiec p（覆蓋率）|Christoffersen p（獨立性）|平均 VaR");
  add("risk.st.epu", "<strong>News-based EPU test:</strong> {v}. Robustness ({spec} specification): {rv}. p &lt; 0.05 in the backtest table means the test rejects correct VaR coverage or independence.",
    "<strong>新聞指標 EPU 檢驗：</strong>{v}。穩健性（{spec} 規格）：{rv}。回測表中 p &lt; 0.05 代表檢定否定了 VaR 的覆蓋率或獨立性。");
  add("epu.keep", "keep: EPU significantly improves forecasts", "保留：EPU 顯著改善預測");
  add("epu.drop.nosig", "drop: no significant improvement from EPU (pre-set rule: improvement with DM t ≥ 2 at every horizon)", "移除：EPU 沒有顯著改善（事先規則：每個期間都需改善且 DM t ≥ 2）");
  add("epu.drop.worse", "drop: EPU significantly worsens forecasts", "移除：EPU 顯著使預測變差");
  add("epu.drop.oneSpec", "drop: EPU helps under one specification only", "移除：EPU 只在單一規格下有幫助");
  add("spec.log", "log", "對數");
  add("spec.level", "level", "原始數值");
  add("hz", "{h}d", "{h} 日");
  add("model.ewma", "EWMA (RiskMetrics 0.94)", "EWMA（RiskMetrics 0.94）");
  add("model.har", "HAR", "HAR");
  add("model.har_vix", "HAR + VIX", "HAR + VIX");
  add("model.har_vix_epu", "HAR + VIX + EPU", "HAR + VIX + EPU");
  add("risk.lt.vol", "Next-month volatility forecast", "下月波動預測");
  add("risk.lt.volSub", "90% band {lo}–{hi} · current 21d {c} · for month after {d}", "90% 區間 {lo}–{hi} · 目前 21 日波動 {c} · 適用 {d} 之後的一個月");
  add("risk.lt.dd", "P(drawdown &gt; 20% in 12m)", "12 個月內跌逾 20% 的機率");
  add("risk.lt.ddSubModel", "model estimate · 90% {lo}–{hi}", "模型估計 · 90% 區間 {lo}–{hi}");
  add("risk.lt.ddSubBase", "historical base rate ({n} months, {e} event months)", "歷史平均（{n} 個月，其中 {e} 個月發生）");
  add("risk.lt.model", "Model estimate (reference only)", "模型估計（僅供參考）");
  add("risk.lt.modelSub", "90% {lo}–{hi} · {d}", "90% 區間 {lo}–{hi} · {d}");
  add("risk.lt.modelSubNo", " · not skillful out-of-sample", " · 樣本外無效");
  add("risk.vf.h2", "Volatility forecast — out-of-sample (predictable)", "波動預測 — 樣本外（可預測）");
  add("risk.vf.f", "Forecast (made at month-end t)", "預測（於月底 t 做出）");
  add("risk.vf.r", "Realized next month", "下個月實際值");
  add("risk.vf.note", "OLS on log 21-day realized vol and log VIX, refit each January. Out-of-sample R² {r2} vs historical mean, {rp} vs 'next month = this month'; correlation {c} over {w}. Volatility clustering makes risk size predictable — not the direction or timing of a crash.",
    "以 21 日實際波動與 VIX 的對數做迴歸，每年 1 月重新估計。樣本外 R²：相對歷史平均 {r2}，相對「下月＝本月」{rp}；相關係數 {c}，期間 {w}。波動有聚集性，所以「風險大小」可以預測，但崩盤的方向與時間點不行。");
  add("risk.sk.h2", "Drawdown-event model — out-of-sample skill vs the base rate", "大跌事件模型 — 樣本外表現 vs 歷史平均");
  add("risk.sk.cols", "Target (DD worse than)|Model|Event months|Brier|Brier (base rate)|BSS|90% CI|AUC|Verdict", "目標（回撤超過）|模型|發生月數|Brier|Brier（歷史平均）|BSS|90% 信賴區間|AUC|判讀");
  add("risk.sk.full", "Vol + earnings + momentum", "波動＋獲利＋動能");
  add("risk.sk.vol", "Vol only", "只有波動");
  add("risk.sk.target", "{h}m, {c}%", "{h} 個月，{c}%");
  add("risk.sk.note", "Brier skill score (BSS) = 1 − Brier(model) / Brier(base rate). Above 0 means better than always forecasting the historical frequency. 90% CI from a 12-month moving-block bootstrap. \"Episodes\" counts separate runs of event months: overlapping 12-month windows make many event months from one crash.",
    "Brier 技能分數（BSS）＝ 1 − Brier（模型）÷ Brier（歷史平均）。大於 0 代表比「永遠預測歷史頻率」更好。90% 信賴區間以 12 個月區塊 bootstrap 估計。「次數」是指獨立的大跌事件：12 個月區間重疊，所以一次崩盤會產生很多個「發生月」。");
  add("skill.skillful", "skillful", "有效");
  add("skill.noskill", "no skill", "無效");
  add("skill.nodemo", "no demonstrated skill", "未證明有效");
  add("skill.inconclusive", "inconclusive", "不確定");
  add("skill.full.skillful", "skillful: beats the base rate out-of-sample", "有效：樣本外勝過歷史平均");
  add("skill.full.noskill", "no skill: worse than the base rate out-of-sample - use the base rate", "無效：樣本外比歷史平均更差，應改用歷史平均");
  add("skill.full.nodemo", "no demonstrated skill: not better than the base rate - use the base rate", "未證明有效：沒有比歷史平均好，應改用歷史平均");
  add("skill.full.inconclusive", "inconclusive: positive but uncertain skill", "不確定：略有正效果但不確定");
  add("risk.era.h2", "By era (12-month, −20% target)", "分時期（12 個月，−20% 目標）");
  add("risk.era.cols", "Era|Months|Event months|Episodes|AUC|BSS", "時期|月數|發生月數|事件次數|AUC|BSS");
  add("risk.pr.h2", "Out-of-sample probability vs what happened", "樣本外機率 vs 實際發生");
  add("risk.pr.pick", "Target", "目標");
  add("risk.pr.event", "Event happened (1 = yes)", "實際發生（1 = 是）");
  add("risk.pr.model", "Model probability", "模型機率");
  add("risk.pr.base", "Base rate (expanding)", "歷史平均（擴張視窗）");
  add("risk.target.dd20_12m", "P(drawdown worse than -20% within 12 months)", "12 個月內回撤超過 20% 的機率");
  add("risk.target.dd10_6m", "P(drawdown worse than -10% within 6 months)", "6 個月內回撤超過 10% 的機率");
  add("risk.rel.h2", "Reliability (calibration) — predicted vs observed frequency", "校準度 — 預測機率 vs 實際頻率");
  add("risk.rel.obs", "Observed vs predicted", "實際 vs 預測");
  add("risk.rel.perfect", "Perfect calibration", "完美校準");
  add("risk.rel.x", "Mean predicted probability", "平均預測機率");
  add("risk.rel.y", "Observed frequency", "實際頻率");
  add("risk.rel.cols", "Predicted bin|Months|Mean predicted|Observed", "預測區間|月數|平均預測|實際");
  add("risk.drv.h2", "Current model drivers (log-odds contribution vs average)", "目前模型的影響因子（相對平均的對數勝算貢獻）");
  add("risk.drv.cols", "Feature|Value|Coefficient (per sd)|Log-odds contribution", "特徵|數值|係數（每個標準差）|對數勝算貢獻");
  add("feat.log_rv63", "log 63d realized vol", "63 日實際波動（對數）");
  add("feat.log_vix", "log VIX (monthly mean)", "VIX 月平均（對數）");
  add("feat.earn_score", "Earnings momentum score", "獲利動能分數");
  add("feat.px_z", "Price extension z (momentum)", "股價偏離 z（動能）");
  add("risk.footer", "L2 logistic, standardized features · refit annually (January); labels must be fully known before the predicted year · drawdowns from month-end closes (understates intra-month lows) · engine {ver}",
    "L2 邏輯迴歸，特徵標準化 · 每年 1 月重新估計；訓練標籤必須在預測年度之前完全確定 · 回撤以月底收盤價計算（會低估月中低點）· 引擎 {ver}");

  const lang = detect();

  function t(key, params) {
    let s = D[lang][key];
    if (s === undefined) { s = D.en[key]; if (s !== undefined && lang !== "en") console.warn("i18n missing " + lang + ": " + key); }
    if (s === undefined) { console.warn("i18n missing key: " + key); return key; }
    if (params) s = s.replace(/\{(\w+)\}/g, (m, k) => (params[k] === undefined || params[k] === null ? m : String(params[k])));
    return s;
  }
  const has = (key) => D[lang][key] !== undefined || D.en[key] !== undefined;
  const cols = (key) => t(key).split("|");

  function apply(root) {
    const r = root || document;
    r.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    r.querySelectorAll("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
    r.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  }

  function setLang(l) {
    try { localStorage.setItem(STORE_KEY, l); } catch (e) { /* storage blocked: still switch via URL */ }
    const u = new URL(location.href);
    u.searchParams.set("lang", l);
    location.href = u.toString();
  }

  function mountSwitch() {
    const nav = document.querySelector(".nav-links");
    if (!nav) return;
    const b = document.createElement("button");
    b.type = "button";
    b.className = "lang-switch";
    b.textContent = t("lang.switch");
    b.title = t("lang.switch.title");
    b.setAttribute("lang", lang === "en" ? "zh-TW" : "en");
    b.addEventListener("click", () => setLang(lang === "en" ? "zh-TW" : "en"));
    nav.appendChild(b);
    // Keep the chosen language when following internal links.
    if (lang !== "en" || new URLSearchParams(location.search).has("lang")) {
      document.querySelectorAll("a[href$='.html']").forEach((a) => {
        const u = new URL(a.getAttribute("href"), location.href);
        u.searchParams.set("lang", lang);
        a.setAttribute("href", u.pathname.split("/").pop() + u.search);
      });
    }
  }

  document.documentElement.lang = lang;
  function init() {
    apply();
    mountSwitch();
    if (document.body.dataset.i18nTitle) document.title = t(document.body.dataset.i18nTitle);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();

  global.TCD_I18N = { lang, t, has, cols, apply, setLang };
})(window);
