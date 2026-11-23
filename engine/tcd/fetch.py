"""Download (or load cached) raw inputs into typed objects."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import SEC_SHARE_TAGS, SEC_TAGS, UNIVERSE, EngineConfig
from .sources import fred, sec, yahoo
from .sources.http import FetchError
from .sources.store import RawStore

log = logging.getLogger(__name__)

FRED_SERIES = {
    "tbill_3m": "DTB3",  # 3-month T-bill, % (daily)
    "it_invest": "A679RC1Q027SBEA",  # information processing equipment investment (quarterly)
    "gdp": "GDP",  # nominal GDP (quarterly)
    "corp_profits": "CP",  # corporate profits after tax (quarterly)
    "vix_fred": "VIXCLS",  # VIX fallback (daily, T+1)
}


@dataclass
class RawData:
    ndx: pd.DataFrame
    xlk: pd.DataFrame
    vix: pd.Series
    fred: dict[str, pd.Series]
    sec_facts: dict[str, dict[str, pd.DataFrame]]  # ticker -> metric -> facts
    manifest: dict[str, dict]
    warnings: list[str] = field(default_factory=list)
    prices: dict[str, pd.Series] = field(default_factory=dict)  # ticker -> split-adjusted close
    splits: dict[str, pd.Series] = field(default_factory=dict)  # ticker -> split ratios
    shares: dict[str, pd.DataFrame] = field(default_factory=dict)  # ticker -> share-count facts


def fetch_all(cache_dir: Path, cfg: EngineConfig, offline: bool = False) -> RawData:
    store = RawStore(Path(cache_dir), offline=offline, timeout=cfg.fetch.timeout_s, retries=cfg.fetch.retries)
    warnings: list[str] = []

    ndx = yahoo.fetch_daily(store, "^NDX")
    xlk = yahoo.fetch_daily(store, "XLK")
    fred_data = {key: fred.fetch_series(store, sid) for key, sid in FRED_SERIES.items()}

    try:
        vix = yahoo.fetch_daily(store, "^VIX")["close"]
        # Yahoo is primary (same-day close); FRED fills gaps.
        vix = vix.combine_first(fred_data["vix_fred"])
    except FetchError as exc:
        warnings.append(f"Yahoo ^VIX unavailable, using FRED VIXCLS (T+1): {exc}")
        vix = fred_data["vix_fred"]

    sec_facts: dict[str, dict[str, pd.DataFrame]] = {}
    shares: dict[str, pd.DataFrame] = {}
    prices: dict[str, pd.Series] = {}
    splits: dict[str, pd.Series] = {}
    for company in UNIVERSE:
        try:
            cf = sec.fetch_companyfacts(store, company, cfg.fetch.user_agent, cfg.fetch.sec_pause_s)
        except FetchError as exc:
            # One missing name is tolerable (chain-linking handles it); DQ
            # gates enforce a minimum name count downstream.
            warnings.append(f"SEC {company.ticker} unavailable: {exc}")
            continue
        sec_facts[company.ticker] = {metric: sec.extract_facts(cf, tags) for metric, tags in SEC_TAGS.items()}
        shares[company.ticker] = sec.extract_share_facts(cf, SEC_SHARE_TAGS)
        try:
            px, sp = yahoo.fetch_daily_with_splits(store, company.ticker)
            prices[company.ticker], splits[company.ticker] = px["close"], sp
        except FetchError as exc:
            warnings.append(f"Yahoo {company.ticker} unavailable (excluded from P/E): {exc}")

    store.save_manifest()
    return RawData(ndx=ndx, xlk=xlk, vix=vix.sort_index(), fred=fred_data, sec_facts=sec_facts,
                   manifest=dict(store.manifest), warnings=warnings,
                   prices=prices, splits=splits, shares=shares)
