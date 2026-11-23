"""Multi-market panel for the market VaR METHOD (methodology section 20).

Registered 2026-11-23, before any result of the panel was computed.

The live market VaR is one series, so a live verdict on it takes a year or
more. To judge the METHOD sooner, the same method is applied to ten other
US-listed index / ETF series and logged daily in the market ledger as
`panel_var_1d:<symbol>`:

    method: log-HAR on (rv_d, rv_w, rv_m) of the series' own daily log returns,
            one-day target, annual walk-forward refits (training targets known
            by the end of the previous year), Duan smearing; 1-day 95% VaR from
            the 5% quantile of all earlier OUT-OF-SAMPLE standardized returns
            (expanding, >= 500) - i.e. the live VaR's rule WITHOUT the VIX term
            (VIX measures US large-cap equity volatility only).
    series: ^NDX ^SOX SPY XLF XLE XLV EWJ EWG EWU EEM (Yahoo adjusted close).

The pooled verdict ("too many breaches") uses the registered interim looks of
sequential.py on the first 60 / 120 / 250 scored dates. It is a verdict on the
method, not on the XLK VaR shown on the site.
"""
from __future__ import annotations

from math import exp, sqrt

import numpy as np
import pandas as pd

from .short_risk import design, fit_var

SYMBOLS = ("^NDX", "^SOX", "SPY", "XLF", "XLE", "XLV", "EWJ", "EWG", "EWU", "EEM")
FEATS = ["rv_d", "rv_w", "rv_m"]
LOG_FLOOR = 1e-8
VAR_FLOOR = 1e-8
MIN_TRAIN = 1000
MIN_OOS = 500
LEVEL = 0.05
EWMA_LAMBDA = 0.94


def frame(close: pd.Series) -> pd.DataFrame:
    c = close.dropna()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    r = np.log(c).diff().dropna()
    df = pd.DataFrame({"r": r})
    r2 = r ** 2
    df["rv_d"], df["rv_w"], df["rv_m"] = r2, r2.rolling(5).mean(), r2.rolling(22).mean()
    df["r_next"] = r.shift(-1)
    df["y1"] = df["r_next"] ** 2
    ew = np.empty(len(df))
    ew[0] = float(r2.iloc[:22].mean())
    for i in range(1, len(df)):
        ew[i] = EWMA_LAMBDA * ew[i - 1] + (1 - EWMA_LAMBDA) * float(r2.iloc[i])
    df["ewma"] = ew
    return df


def walk_forward(df: pd.DataFrame) -> pd.Series:
    """Out-of-sample next-day variance forecasts (annual refits)."""
    X = design(df, FEATS, "log", LOG_FLOOR)
    ok = ~np.isnan(X).any(axis=1)
    y = df["y1"].to_numpy(float)
    idx = df.index
    pos = np.arange(len(idx))
    f = pd.Series(np.nan, index=idx)
    for Y in range(int(idx[0].year) + 1, int(idx[-1].year) + 1):
        train_end = pd.Timestamp(f"{Y - 1}-12-31")
        end_pos = np.minimum(pos + 1, len(idx) - 1)
        known = (idx[end_pos] <= train_end) & (pos + 1 < len(idx))
        tr = ok & known & ~np.isnan(y)
        te = (idx.year == Y) & ok
        if tr.sum() < MIN_TRAIN or not te.any():
            continue
        m = fit_var(X[tr], y[tr], FEATS, "log", LOG_FLOOR)
        f[te] = m.predict(X[te], VAR_FLOOR)
    return f


def forecast(close: pd.Series) -> dict | None:
    """Current forecast from the latest close, plus the backtest (context only)."""
    df = frame(close)
    if len(df) < MIN_TRAIN + MIN_OOS:
        return None
    f = walk_forward(df)
    X = design(df, FEATS, "log", LOG_FLOOR)
    ok = ~np.isnan(X).any(axis=1)
    y = df["y1"].to_numpy(float)
    tr = ok & ~np.isnan(y)
    m = fit_var(X[tr], y[tr], FEATS, "log", LOG_FLOOR)
    fv = float(m.predict(X[-1:], VAR_FLOOR)[0])
    z = (df["r_next"] / np.sqrt(f)).where(f.notna()).dropna()
    if len(z) < MIN_OOS:
        return None
    q = float(np.quantile(z, LEVEL))
    # Backtest context: expanding OOS quantile known before each day.
    qs = z.expanding(MIN_OOS).quantile(LEVEL).shift(1).reindex(df.index)
    okb = f.notna() & qs.notna() & df["r_next"].notna()
    br = (df["r_next"] < qs * np.sqrt(f))[okb].to_numpy()
    return {"date": str(df.index[-1].date()), "var95": float(1 - exp(q * sqrt(fv))), "har_var": fv,
            "ewma_var": float(df["ewma"].iloc[-1]), "quantile": q,
            "backtest_context": {"n": int(len(br)), "rate": float(br.mean()) if len(br) else None,
                                 "rate_last_3y": float(br[-756:].mean()) if len(br) else None}}


def run(prices: dict[str, pd.DataFrame]) -> dict:
    out, skipped = {}, []
    for s in SYMBOLS:
        px = prices.get(s)
        try:
            fc = forecast(px["adjclose"]) if px is not None else None
        except Exception:  # noqa: BLE001 - one bad series must not drop the panel
            fc = None
        if fc is None:
            skipped.append(s)
        else:
            out[s] = fc
    return {"forecasts": out, "skipped": skipped}


def returns(prices: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
    """Daily log returns used to score the panel forecasts."""
    out = {}
    for s in SYMBOLS:
        px = prices.get(s)
        if px is not None:
            c = px["adjclose"].dropna()
            c = c[~c.index.duplicated(keep="last")].sort_index()
            out[s] = np.log(c).diff().dropna()
    return out
