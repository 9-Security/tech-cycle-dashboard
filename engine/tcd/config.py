"""Engine configuration.

Everything that changes results lives here so a run is reproducible from
(config, raw data manifest, git sha).
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from itertools import product
from typing import Iterator

ENGINE_VERSION = "3.2.0"

REGIME_LABELS = {1: "Overheat", 2: "Shock", 3: "Digestion", 4: "Normal"}
REGIME_COLORS = {1: "#c45c26", 2: "#8b1e3f", 3: "#b08900", 4: "#2f6f4e"}


@dataclass(frozen=True)
class Company:
    ticker: str
    cik: int


# Fixed "tech Capex" universe. NOTE: chosen with hindsight (today's leaders);
# see docs/methodology.md "Survivorship" for the caveat.
UNIVERSE: tuple[Company, ...] = (
    Company("AAPL", 320193),
    Company("MSFT", 789019),
    Company("AMZN", 1018724),
    Company("GOOGL", 1652044),
    Company("META", 1326801),
    Company("NVDA", 1045810),
    Company("ORCL", 1341439),
    Company("AMD", 2488),
    Company("INTC", 50863),
    Company("AVGO", 1730168),
)

# XBRL tags in priority order (first tag that has a value for a period wins).
SEC_TAGS: dict[str, tuple[str, ...]] = {
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
    ),
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "net_income": (
        "NetIncomeLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "ProfitLoss",
    ),
}

# Share counts (unit "shares"), priority order. Duration (weighted average)
# and instant (period-end) facts are both accepted.
SEC_SHARE_TAGS: tuple[str, ...] = (
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
    "CommonStockSharesOutstanding",
)

SEC_FORMS = ("10-Q", "10-K", "10-Q/A", "10-K/A", "10-KT")


@dataclass(frozen=True)
class RegimeParams:
    """Thresholds and per-regime risk weights (the tunable 'card')."""

    vix_threshold: float = 22.0
    overheat_threshold: float = 1.25
    earn_threshold: float = -1.0  # earnings-momentum score (in rolling std units)
    w_overheat: float = 0.6
    w_shock: float = 0.25
    w_digestion: float = 0.6
    w_normal: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ParamGrid:
    """Search space for walk-forward tuning. Kept small on purpose:
    every extra combination raises the multiple-testing haircut (DSR)."""

    vix_threshold: tuple[float, ...] = (18.0, 20.0, 22.0, 25.0, 28.0, 32.0)
    overheat_threshold: tuple[float, ...] = (0.75, 1.0, 1.25, 1.5, 2.0)
    earn_threshold: tuple[float, ...] = (-2.0, -1.5, -1.0, -0.5)
    w_overheat: tuple[float, ...] = (0.5, 0.75)
    w_shock: tuple[float, ...] = (0.0, 0.25, 0.5)
    w_digestion: tuple[float, ...] = (0.5, 0.75)

    def __iter__(self) -> Iterator[RegimeParams]:
        for v, o, e, wo, ws, wd in product(
            self.vix_threshold,
            self.overheat_threshold,
            self.earn_threshold,
            self.w_overheat,
            self.w_shock,
            self.w_digestion,
        ):
            yield RegimeParams(v, o, e, wo, ws, wd, 1.0)

    def __len__(self) -> int:
        return (
            len(self.vix_threshold)
            * len(self.overheat_threshold)
            * len(self.earn_threshold)
            * len(self.w_overheat)
            * len(self.w_shock)
            * len(self.w_digestion)
        )


@dataclass(frozen=True)
class TiltParams:
    """v3 continuous model: valuation / Capex tilts (signs learned by
    walk-forward), optional earnings cut, volatility targeting."""

    c_px: float = 0.0  # weight change per +1 sd of price extension (momentum-like)
    c_pe: float = 0.0  # weight change per +1 sd of aggregate P/E z (0 before P/E exists)
    c_capex: float = 0.0  # weight change per +1 sd of capex_z
    base: float = 1.0  # exposure before tilts
    earn_cut: float = 1.0  # multiplier when earnings score < earn_threshold (1.0 = off)
    earn_threshold: float = -1.0
    vol_input: str = "rv63"  # rv21 | rv63 | vix
    vol_target: float = float("inf")  # annualized; inf = off
    band: float = 0.05  # no-trade band on weight changes

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TiltGrid:
    # 0 first: walk-forward ties (e.g. a coefficient with no data yet) go to the simplest model.
    c_px: tuple[float, ...] = (0.0, -0.25, 0.25)
    c_pe: tuple[float, ...] = (0.0, -0.25, 0.25)
    c_capex: tuple[float, ...] = (0.0, -0.25, 0.25)
    base: tuple[float, ...] = (1.0, 0.75)
    earn: tuple[tuple[float, float], ...] = ((1.0, -1.0), (0.75, -1.0))  # (cut, threshold); off first
    vol: tuple[tuple[str, float], ...] = (
        ("rv63", float("inf")),
        ("rv21", 0.15), ("rv21", 0.20), ("rv21", 0.25),
        ("rv63", 0.15), ("rv63", 0.20), ("rv63", 0.25),
        ("vix", 0.15), ("vix", 0.20), ("vix", 0.25),
    )

    def __iter__(self) -> Iterator[TiltParams]:
        for cx, cp, cc, b, (ec, et), (vi, vt) in product(self.c_px, self.c_pe, self.c_capex, self.base, self.earn, self.vol):
            yield TiltParams(cx, cp, cc, b, ec, et, vi, vt)

    def __len__(self) -> int:
        return len(self.c_px) * len(self.c_pe) * len(self.c_capex) * len(self.base) * len(self.earn) * len(self.vol)


# Date the v3 design was fixed. Months after it are a true holdout for v3:
# the design itself was chosen after seeing full-sample signal studies.
V3_DESIGN_DATE = "2026-11-23"


@dataclass(frozen=True)
class PromotionRule:
    """Pre-registered rule for promoting v3 to the live model (docs/model-promotion.md).
    The engine only REPORTS the status; it never switches models."""

    min_months: int = 24  # post-design months before any decision
    retire_months: int = 36  # still failing at this point -> retire the candidate
    mdd_tolerance: float = 0.05  # v3 MDD may be at most 5 pts worse than vol-matched B&H
    max_refresh_gap_days: int = 7  # longest allowed gap between successful daily refreshes
    # Fingerprint of the frozen v3 specification at the design date. Any change
    # to it resets the evaluation clock (new design date + new fingerprint).
    spec_fingerprint: str = "88e42dfdbee76632762785a306dab4136ce7ebdacf2aa8fd9941c8c23faab61d"


@dataclass(frozen=True)
class FeatureConfig:
    # Valuation: "pe" = aggregate mega-cap P/E (SEC + Yahoo) where available,
    # price-extension proxy before; "price_ext" = proxy only (v2.0 behaviour).
    valuation: str = "pe"
    pe_z_window: int = 120
    pe_z_min: int = 36
    shares_stale_days: int = 200
    # Valuation proxy: price extension = close / MA(ma_days) - 1, z-scored.
    val_ma_days: int = 252
    val_z_window: int = 120
    val_z_min: int = 60
    # Capex intensity z-score.
    capex_z_window: int = 120
    capex_z_min_firm: int = 36
    capex_z_min_proxy: int = 60
    # Earnings momentum: 3m growth of TTM earnings / rolling std.
    earn_growth_months: int = 3
    earn_std_window: int = 60
    earn_std_min_firm: int = 24
    earn_std_min_proxy: int = 36
    # Realized volatility windows (trading days) for vol targeting; VIX is
    # mapped to tech vol with a trailing median ratio (PIT).
    vix_ratio_months: int = 36
    # VIX monthly statistic: "mean" (month average) or "last" (month-end close).
    vix_stat: str = "mean"
    # BEA macro proxies: availability lag after quarter end (conservative;
    # FRED values are latest vintage, so revisions are a residual bias).
    macro_lag_days: int = 90
    # SEC: drop a company's TTM if its latest quarter ended > this many days ago.
    sec_stale_days: int = 200
    sec_min_names: int = 3
    # Hand-labelled shock events are deliberately NOT supported: labelling
    # "DotCom" or "Lehman" months is hindsight and leaks the answer.


@dataclass(frozen=True)
class BacktestConfig:
    cost_bps: float = 15.0  # one-way, per unit of weight change
    train_start: str = "1993-01-31"  # first month that may enter a training window
    oos_start_year: int = 2000  # first walk-forward test year
    wf_step_months: int = 12
    # Objective: Sharpe minus penalty for drawdowns beyond mdd_budget.
    mdd_budget: float = 0.30
    mdd_penalty: float = 2.0
    min_train_months: int = 84


@dataclass(frozen=True)
class FetchConfig:
    user_agent: str = field(
        default_factory=lambda: os.environ.get(
            "SEC_USER_AGENT",
            # SEC asks for "<org/app> <contact email>"; set SEC_USER_AGENT in CI.
            "tech-cycle-dashboard/2.0 research",
        )
    )
    timeout_s: float = 60.0
    retries: int = 4
    sec_pause_s: float = 0.25  # SEC fair-access: well under 10 req/s


@dataclass(frozen=True)
class EngineConfig:
    features: FeatureConfig = field(default_factory=FeatureConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    grid: ParamGrid = field(default_factory=ParamGrid)
    tilt_grid: TiltGrid = field(default_factory=TiltGrid)
    promotion: PromotionRule = field(default_factory=PromotionRule)
    fetch: FetchConfig = field(default_factory=FetchConfig)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fetch"].pop("user_agent", None)
        d["grid"]["n_combinations"] = len(self.grid)
        d["tilt_grid"]["n_combinations"] = len(self.tilt_grid)
        return d
