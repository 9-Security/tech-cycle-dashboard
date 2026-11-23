"""Monthly point-in-time feature panel.

Every column at month-end t uses only information available on or before t.
The last row may be a *partial* (in-progress) month: it carries provisional
signals for the daily status view and is excluded from backtests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay,
                                    USMartinLutherKingJr, USMemorialDay, USPresidentsDay,
                                    USThanksgivingDay, nearest_workday, sunday_to_monday)

from . import fundamentals as fx
from .config import FeatureConfig
from .fetch import RawData


def rolling_z(x: pd.Series, window: int, min_periods: int) -> pd.Series:
    mu = x.rolling(window, min_periods=min_periods).mean()
    sd = x.rolling(window, min_periods=min_periods).std()
    return (x - mu) / sd.replace(0.0, np.nan)


def asof_monthly(values: pd.Series, available: pd.Series, months: pd.DatetimeIndex) -> pd.Series:
    """Latest value whose availability date <= each month-end."""
    left = pd.DataFrame({"m": pd.DatetimeIndex(months).astype("datetime64[ns]")})
    right = (
        pd.DataFrame({"a": pd.DatetimeIndex(available.values).astype("datetime64[ns]"), "v": values.values})
        .dropna()
        .sort_values("a")
    )
    merged = pd.merge_asof(left, right, left_on="m", right_on="a", direction="backward")
    return pd.Series(merged["v"].values, index=months)


def macro_quarterly_asof(s: pd.Series, months: pd.DatetimeIndex, lag_days: int) -> pd.Series:
    """FRED quarterly series (dated at quarter start) made PIT with a release lag."""
    q_end = s.index + pd.offsets.QuarterEnd(0)
    available = pd.Series(q_end + pd.Timedelta(days=lag_days))
    return asof_monthly(s.reset_index(drop=True), available, months)


def month_index(raw: RawData) -> tuple[pd.DatetimeIndex, pd.Timestamp, bool]:
    last_obs = min(raw.xlk.index.max(), raw.ndx.index.max())
    start = raw.ndx.index.min() + pd.offsets.MonthEnd(0)
    end = last_obs + pd.offsets.MonthEnd(0)
    months = pd.date_range(start, end, freq="ME")
    last_bday = last_trading_day_of_month(last_obs)
    partial = last_obs.normalize() < last_bday.normalize()
    return months, last_obs, bool(partial)


class NYSECalendar(AbstractHolidayCalendar):
    """NYSE full-day closures (rules since 2022; Juneteenth only from 2022).
    Used only to decide whether the latest month is complete."""
    rules = [
        Holiday("New Year", month=1, day=1, observance=sunday_to_monday),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]


def last_trading_day_of_month(d: pd.Timestamp) -> pd.Timestamp:
    """Last NYSE trading day of d's month (BMonthEnd ignored exchange holidays,
    so a month ending on e.g. Good Friday or Memorial Day was flagged partial)."""
    end = d + pd.offsets.MonthEnd(0)
    hol = NYSECalendar().holidays(end - pd.Timedelta(days=10), end)
    day = end
    while day.weekday() >= 5 or day in hol:
        day -= pd.Timedelta(days=1)
    return day


def _monthly_last(daily: pd.Series, months: pd.DatetimeIndex) -> pd.Series:
    return daily.resample("ME").last().reindex(months)


def build_panel(raw: RawData, cfg: FeatureConfig) -> pd.DataFrame:
    months, last_obs, partial = month_index(raw)
    p = pd.DataFrame(index=months)
    p.index.name = "date"

    # --- Returns -----------------------------------------------------------
    ndx_m = _monthly_last(raw.ndx["close"], months)
    xlk_m = _monthly_last(raw.xlk["adjclose"], months)
    ret_ndx = ndx_m.pct_change(fill_method=None)
    ret_xlk = xlk_m.pct_change(fill_method=None)
    p["risk_ret"] = ret_xlk.where(ret_xlk.notna(), ret_ndx)
    p["risk_src"] = np.where(ret_xlk.notna(), "XLK", "NDX")

    tbill = _monthly_last(raw.fred["tbill_3m"].ffill(), months).ffill()
    p["tbill_pct"] = tbill
    # Yield known at the previous month-end earns this month.
    p["safe_ret"] = tbill.shift(1) / 100.0 / 12.0

    # --- Realized volatility of the risk asset (for vol targeting) -----------
    px = raw.xlk["adjclose"].reindex(raw.ndx.index.union(raw.xlk.index))
    ndx_close = raw.ndx["close"].reindex(px.index)
    dret = np.log(px).diff().where(px.notna() & px.shift(1).notna(), np.log(ndx_close).diff())
    for w in (21, 63):
        rv = dret.rolling(w, min_periods=int(w * 0.8)).std() * np.sqrt(252)
        p[f"rv{w}"] = _monthly_last(rv, months)

    # --- VIX -----------------------------------------------------------------
    vix = raw.vix.resample("ME")
    p["vix"] = (vix.mean() if cfg.vix_stat == "mean" else vix.last()).reindex(months)
    p["vix_last"] = vix.last().reindex(months)
    # Tech vol implied by VIX: VIX x trailing median(realized tech vol / VIX).
    ratio = (p["rv63"] / (p["vix_last"] / 100.0)).rolling(cfg.vix_ratio_months, min_periods=12).median()
    p["vix_tech_ratio"] = ratio
    p["vol_vix"] = p["vix_last"] / 100.0 * ratio

    # --- Valuation proxy: price extension vs long moving average -------------
    ndx = raw.ndx["close"]
    ext = ndx / ndx.rolling(cfg.val_ma_days, min_periods=cfg.val_ma_days).mean() - 1.0
    p["val_ext"] = _monthly_last(ext, months)
    p["val_z_proxy"] = rolling_z(p["val_ext"], cfg.val_z_window, cfg.val_z_min)

    # --- Capex intensity --------------------------------------------------------
    it = raw.fred["it_invest"]
    gdp = raw.fred["gdp"].reindex(it.index)
    proxy_ratio = macro_quarterly_asof((it / gdp).dropna(), months, cfg.macro_lag_days)
    p["capex_ratio_proxy"] = proxy_ratio
    p["capex_z_proxy"] = rolling_z(proxy_ratio, cfg.capex_z_window, cfg.capex_z_min_proxy)

    capex_ttm, rev_ttm, ni_ttm = {}, {}, {}
    for ticker, metrics in raw.sec_facts.items():
        capex_ttm[ticker] = fx.monthly_ttm(fx.quarterly(metrics["capex"]), months, cfg.sec_stale_days)
        rev_ttm[ticker] = fx.monthly_ttm(fx.quarterly(metrics["revenue"]), months, cfg.sec_stale_days)
        ni_ttm[ticker] = fx.monthly_ttm(fx.quarterly(metrics["net_income"]), months, cfg.sec_stale_days)
    capex_df = pd.DataFrame(capex_ttm, index=months).abs()  # outflows sometimes signed
    rev_df = pd.DataFrame(rev_ttm, index=months)
    ni_df = pd.DataFrame(ni_ttm, index=months)

    firm_ratio, n_capex = fx.chain_link(capex_df, rev_df, cfg.sec_min_names)
    p["capex_ratio_firm"] = firm_ratio
    p["n_capex_names"] = n_capex
    p["capex_z_firm"] = rolling_z(firm_ratio, cfg.capex_z_window, cfg.capex_z_min_firm)
    p["capex_z"], p["capex_src"] = _splice(p["capex_z_firm"], p["capex_z_proxy"])

    # --- Earnings momentum (EPS-revision proxy) --------------------------------
    k = cfg.earn_growth_months
    ni_level, n_ni = fx.chain_link(ni_df, None, cfg.sec_min_names)
    g_firm = ni_level / ni_level.shift(k) - 1.0
    p["n_earn_names"] = n_ni
    p["earn_g_firm"] = g_firm
    p["earn_score_firm"] = g_firm / g_firm.rolling(cfg.earn_std_window, min_periods=cfg.earn_std_min_firm).std()

    cp = macro_quarterly_asof(raw.fred["corp_profits"], months, cfg.macro_lag_days)
    g_proxy = cp / cp.shift(k) - 1.0
    p["earn_g_proxy"] = g_proxy
    p["earn_score_proxy"] = g_proxy / g_proxy.rolling(cfg.earn_std_window, min_periods=cfg.earn_std_min_proxy).std()
    p["earn_score"], p["earn_src"] = _splice(p["earn_score_firm"], p["earn_score_proxy"])

    # --- Valuation: aggregate mega-cap P/E (market cap / TTM net income) ------
    mcap = {}
    for ticker, px in raw.prices.items():
        if ticker not in ni_df.columns:
            continue
        sh = fx.monthly_shares(raw.shares.get(ticker, pd.DataFrame(columns=["end", "val", "filed", "priority"])),
                               raw.splits.get(ticker), months, cfg.shares_stale_days)
        mcap[ticker] = _monthly_last(px, months) * sh
    mcap_df = pd.DataFrame(mcap, index=months).reindex(columns=ni_df.columns)
    pe, n_pe = fx.chain_link(mcap_df, ni_df, cfg.sec_min_names)
    p["pe_agg"] = pe  # chain-linked INDEX (continuous across membership changes): used for the z-score only
    p["n_pe_names"] = n_pe
    # Actual aggregate P/E level, sum(market cap) / sum(TTM net income) over the
    # names valid this month (NI > 0). This is the number to show as "P/E x";
    # it jumps when names enter or leave, which is why the z-score uses pe_agg.
    ok = mcap_df.notna() & ni_df.notna() & (ni_df > 0)
    lvl = mcap_df.where(ok).sum(axis=1, min_count=1) / ni_df.where(ok).sum(axis=1, min_count=1)
    p["pe_level"] = lvl.where(ok.sum(axis=1) >= cfg.sec_min_names)
    p["mcap_agg_bn"] = mcap_df.where(ni_df > 0).sum(axis=1, min_count=1) / 1e9
    p["val_z_pe"] = rolling_z(np.log(pe), cfg.pe_z_window, cfg.pe_z_min)
    if cfg.valuation == "pe":
        p["val_z"], p["val_src"] = _splice(p["val_z_pe"], p["val_z_proxy"])
        p["val_src"] = p["val_src"].replace({"SEC": "PE", "FRED": "PX"})
    elif cfg.valuation == "price_ext":
        p["val_z"], p["val_src"] = p["val_z_proxy"], pd.Series("PX", index=months)
    else:
        raise ValueError(f"unknown valuation mode {cfg.valuation!r}")

    # --- Composite --------------------------------------------------------------
    p["overheat_score"] = (p["val_z"] + p["capex_z"]) / 2.0

    p["partial"] = False
    if partial:
        p.loc[p.index[-1], "partial"] = True
    p.attrs["last_obs"] = last_obs
    return p


def _splice(firm: pd.Series, proxy: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Use firm-level once it is first valid; proxy before (or if firm gaps)."""
    first = firm.first_valid_index()
    use_firm = firm.notna()
    if first is not None:
        use_firm &= firm.index >= first
    value = firm.where(use_firm, proxy)
    src = pd.Series(np.where(use_firm, "SEC", np.where(proxy.notna(), "FRED", "NA")), index=firm.index)
    return value, src
