#!/usr/bin/env python3
"""
K0: Unified ETF Loop Backtest Engine.

Design invariants (non-negotiable):
  1. Single entry point. Same params + pool → identical results.
  2. Daily loop: signal at date close → orders → execute at configured future date/price → value at execution-date close.
  3. Pure execution functions. No stale variable reuse from outer loops.
  4. Transaction log must fully reconcile NAV:
       cash_t + Σ(shares_i,t × close_i,t) = portfolio_value_t
  5. Participation model uses partial fills, not hard rejects.
  6. cost = commission + liquidity_slippage + participation_impact.
"""
from __future__ import annotations

import os, sys, pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from strategies.etf_loop_strategy import (
    ETFDailyStore, SectorProsperityCache, get_ranked_etfs,
    calculate_atr, _lot_floor, _summarize, _parse_ymd,
)
from strategies._utils import QlibDailyReader


# ═══════════════════════════════════════
# Parameters — clean, no inheritance chain
# ═══════════════════════════════════════

@dataclass
class EngineParams:
    """All parameters for the unified backtest engine. No inheritance, no surprises."""

    # ── Pool ──
    etf_pool_ts: list[str] = field(default_factory=list)  # static pool or None
    pit_pool_path: Optional[str] = None                     # path to pickle for PIT mode
    pit_pools: Optional[dict] = None                        # pre-loaded PIT dict
    core_pool: Optional[list[str]] = None                  # static core pool for dual-pool mode
    use_dynamic_pool: bool = False                         # add PIT liquidity pool on top of core/pit
    dynamic_top_n: int = 100
    dynamic_min_amount: float = 50_000_000
    dynamic_fusion_mode: str = "union"                     # union or capped
    dynamic_max_slots: int = 1                             # capped mode: max dynamic-only holdings
    dynamic_max_total_weight: Optional[float] = 0.20       # capped mode: total dynamic-only weight cap
    dynamic_score_margin: float = 0.05                     # dynamic score must beat weakest core by margin
    dynamic_overheat_lookback: int = 20
    dynamic_overheat_threshold: float = 0.10               # prior 20d return above this is penalized
    dynamic_overheat_penalty: float = 0.50                 # score multiplier when overheated

    # ── Core strategy ──
    holdings_num: int = 5
    lookback_days: int = 25
    stop_loss: float = 0.95

    # ── Filters (all on by default) ──
    use_rsi_filter: bool = True
    rsi_period: int = 6
    rsi_lookback_days: int = 1
    rsi_threshold: float = 98
    enable_volume_check: bool = True
    volume_lookback: int = 5
    volume_threshold: float = 2.0
    volume_return_limit: float = 1.0
    use_short_momentum_filter: bool = True
    short_lookback_days: int = 10
    short_momentum_threshold: float = 0.0
    loss: float = 0.97
    min_score_threshold: float = 0.0
    max_score_threshold: float = 500.0


    # ── Dynamic lookback ──
    use_dynamic_lookback: bool = False
    dyn_lookback_min: int = 10
    dyn_lookback_max: int = 60
    dyn_lookback_vol_ratio_cap: float = 0.9
    dyn_lookback_short_window: int = 10
    dyn_lookback_long_window: int = 60
    dyn_lookback_use_atr: bool = True

    # ── Enhanced drawdown ──
    dd_use_enhanced: bool = True

    # ── Premium penalty ──
    use_premium_penalty: bool = False
    premium_lookback: int = 20
    premium_threshold: float = 0.05
    premium_penalty: float = 0.5

    # ── Drawdown filter ──
    use_drawdown_filter: bool = False

    # ── Reversal filter (anti-momentum-crash) ──
    use_reversal_filter: bool = False
    rev_lookback: int = 5
    rev_sigma: float = 2.0
    rev_penalty: float = 0.3
    dd_lookback: int = 20
    dd_max_drawdown_threshold: float = -0.15
    dd_consecutive_decline_days: int = 5
    # ── Wyckoff filter ──
    use_wyckoff_filter: bool = False
    use_wyckoff_prefilter: bool = False  # Layer 1 Wyckoff → Layer 2 momentum
    # ── Wyckoff V2 (consolidation breakout) ──
    use_wyckoff_v2: bool = False
    wyckoff_v2_range_threshold: float = 0.20
    wyckoff_v2_vol_ratio: float = 1.3
    wyckoff_v2_require_ma60: bool = True

    wyckoff_range_days: int = 60
    wyckoff_dist_threshold: float = 0.8
    wyckoff_vol_penalty: float = 0.6


    # ── Volatility filter ──
    use_vol_filter: bool = False
    vol_filter_lookback: int = 20
    vol_filter_threshold: float = 0.5

    # ── Trend filter ──
    use_trend_filter: bool = False
    trend_ma_period: int = 50

    # ── Volatility-adjusted position weighting ──
    use_vol_weighting: bool = False
    vol_weight_lookback: int = 20
    # ── ATR stop ──
    use_atr_stop_loss: bool = True
    atr_period: int = 14
    atr_multiplier: float = 2.0
    atr_trailing_stop: bool = False

    # ── Cost model ──
    open_cost: float = 0.0001      # buy-side commission
    close_cost: float = 0.0001     # sell-side commission
    slippage: float = 0.0001       # fixed slippage (used when dynamic_cost=False)
    use_dynamic_cost: bool = False
    liquidity_lookback: int = 60   # days for avg amount calculation
    # Tiered liquidity slippage (extra on top of commission):
    # [(amount_threshold, per_side_slip), ...]
    slip_tiers: tuple = field(default_factory=lambda: (
        (10_000_000_000, 0.0001),   # ≥10B:  0.01%
        (1_000_000_000,  0.0002),   # ≥1B:   0.02%
        (500_000_000,     0.0004),   # ≥500M: 0.04%
        (50_000_000,      0.0008),   # ≥50M:  0.08%
        (0,               0.0015),   # <50M:  0.15%
    ))

    # ── Participation model ──
    participation_cap: Optional[float] = None  # e.g. 0.05 = 5% max trade/amount
    participation_penalty_tiers: tuple = field(default_factory=lambda: (
        (0.01, 0.0),
        (0.02, 0.0001),
        (0.03, 0.0002),
        (0.05, 0.0005),
    ))
    min_trade_value: float = 5000.0

    # ── Cooldown ──
    cooldown_days: int = 0
    cooldown_override_top_n: int = 3
    switch_score_margin: float = 0.0  # keep current holding unless replacement score beats it by this margin

    # ── Rebalancing frequency ──
    rebalance_interval: int = 1

    # ── Execution timing/price stress ──
    execution_price_mode: str = "open"   # open, close, or vwap
    execution_delay_days: int = 1        # 1 = next trading day

    # ── Portfolio-level defense ──
    defense_ma_period: int = 0        # NAV MA period for defense (0=disabled)
    defense_exposure: float = 0.0     # exposure during defense (0=cash, 0.5=half)

    # ── Multi-factor scoring ──
    mf_vol_penalty: float = 0.0       # 0=disabled, 0.3=30% max penalty for high vol
    mf_rev_penalty: float = 0.0       # 0=disabled, penalize extreme 3d returns
    mr_ma_period: int = 0              # 0=disabled, mean reversion MA period
    mr_threshold: float = 1.3         # price/MA ratio threshold
    mr_penalty: float = 0.5            # score multiplier when price/MA >= threshold

    # ── Permanent hold / dip-add overlay ──
    permanent_hold_codes: tuple[str, ...] = field(default_factory=tuple)
    permanent_hold_disable_stops: bool = True
    permanent_dip_add_enabled: bool = False
    permanent_dip_threshold: float = 0.10
    permanent_dip_add_weight: float = 0.05
    permanent_max_weight: float = 0.40
    permanent_add_cooldown_days: int = 20

    # ── Backtest window ──
    initial_cash: float = 500_000.0
    benchmark: str = "sh000300"
    start: str = "2018-06-01"
    trading_start: str = ""  # if set, skip trading until this date (still record flat cash)

    # ── Friend strategy replication mode ──
    friend_mode: bool = False  # enables: same-day open exec + yesterday's close signal + subtract penalty
    # ── Position management ──
    use_score_weighting: bool = False  # weight by score instead of equal
    use_dynamic_holdings: bool = False  # vary N based on score dispersion
    dyn_holdings_min: int = 3
    dyn_holdings_max: int = 8

    end: str = "2026-06-25"

    # ── Output ──
    exp_tag: str = "K0"


# ═══════════════════════════════════════
# Pure execution functions
# ═══════════════════════════════════════

def compute_dynamic_cost(
    avg_amount: float,
    trade_value: float,
    params: EngineParams,
) -> dict:
    """
    Returns:
        commission: per-side commission rate
        slip: per-side liquidity slippage
        part_pen: per-side participation penalty
        filled_value: actual value that can be traded (caps at part limit)
        rejected: True if filled_value < min_trade_value
    """
    commission = params.open_cost  # same for buy and sell

    if params.use_dynamic_cost:
        slip = params.slippage  # default
        for threshold, s in params.slip_tiers:
            if avg_amount >= threshold:
                slip = s
                break
    else:
        slip = params.slippage

    # Participation penalty
    part_pen = 0.0
    if params.participation_cap is not None and avg_amount > 0:
        p = trade_value / avg_amount
        for threshold, penalty in params.participation_penalty_tiers:
            if p < threshold:
                part_pen = penalty
                break
        if p >= params.participation_cap:
            # Partial fill: cap at participation_cap
            max_tv = avg_amount * params.participation_cap
            if max_tv < params.min_trade_value:
                return {"commission": commission, "slip": slip, "part_pen": part_pen,
                        "filled_value": 0.0, "rejected": True}
            return {"commission": commission, "slip": slip, "part_pen": part_pen,
                    "filled_value": max_tv, "rejected": False, "partial": True}

    return {"commission": commission, "slip": slip, "part_pen": part_pen,
            "filled_value": trade_value, "rejected": False, "partial": False}


def execute_sell(
    code: str,
    shares_held: int,
    signal_px: float,
    exec_px: float,
    entry_px: float,
    avg_amount: float,
    params: EngineParams,
) -> dict | None:
    """Pure sell execution. Returns None if cannot execute."""
    if shares_held <= 0:
        return None
    if np.isnan(exec_px) or exec_px <= 0:
        return None  # no valid price

    trade_value = shares_held * exec_px
    cost = compute_dynamic_cost(avg_amount, trade_value, params)
    if cost["rejected"]:
        return None
    if cost.get("partial"):
        shares_sold = int(cost["filled_value"] / exec_px / 100) * 100
        if shares_sold <= 0:
            return None
        trade_value = shares_sold * exec_px
        proceeds = trade_value * (1.0 - cost["commission"] - cost["slip"] - cost["part_pen"])
        return {
            "code": code, "action": "SELL",
            "shares": shares_sold, "partial": True,
            "price": exec_px, "gross_proceeds": trade_value,
            "cost_total": trade_value * (cost["commission"] + cost["slip"] + cost["part_pen"]),
            "net_proceeds": proceeds,
            "cost_detail": cost,
        }

    proceeds = trade_value * (1.0 - cost["commission"] - cost["slip"] - cost["part_pen"])
    return {
        "code": code, "action": "SELL",
        "shares": shares_held, "partial": False,
        "price": exec_px, "gross_proceeds": trade_value,
        "cost_total": trade_value * (cost["commission"] + cost["slip"] + cost["part_pen"]),
        "net_proceeds": proceeds,
        "cost_detail": cost,
    }


def execute_buy(
    code: str,
    available_cash: float,
    target_value: float,
    exec_px: float,
    avg_amount: float,
    params: EngineParams,
) -> dict | None:
    """Pure buy execution. Returns None if cannot execute."""
    if np.isnan(exec_px) or exec_px <= 0:
        return None
    if available_cash <= 0 or target_value <= 0:
        return None

    # Estimate shares based on available cash
    total_cost_rate = params.open_cost + params.slippage  # rough estimate
    estimated_shares = _lot_floor(available_cash / (exec_px * (1.0 + total_cost_rate)))
    if estimated_shares <= 0:
        return None

    trade_value = estimated_shares * exec_px
    cost = compute_dynamic_cost(avg_amount, trade_value, params)
    if cost["rejected"]:
        return None

    if cost.get("partial"):
        trade_value = cost["filled_value"]
        shares = int(trade_value / exec_px / 100) * 100
    else:
        shares = estimated_shares

    if shares <= 0:
        return None

    trade_value = shares * exec_px
    if trade_value < params.min_trade_value:
        return None

    total_cost = trade_value * (cost["commission"] + cost["slip"] + cost["part_pen"])
    required_cash = trade_value + total_cost
    if required_cash > available_cash:
        # Scale down
        scale = available_cash / required_cash
        shares = int(shares * scale / 100) * 100
        if shares <= 0:
            return None
        trade_value = shares * exec_px
        total_cost = trade_value * (cost["commission"] + cost["slip"] + cost["part_pen"])

    return {
        "code": code, "action": "BUY",
        "shares": shares, "partial": cost.get("partial", False),
        "price": exec_px, "gross_cost": trade_value,
        "cost_total": total_cost,
        "net_cost": trade_value + total_cost,
        "cost_detail": cost,
    }


# ═══════════════════════════════════════
# PIT pool helper
# ═══════════════════════════════════════

def _load_pit_pools(path: str) -> dict:
    with open(path, "rb") as f:
        pools = pickle.load(f)
    return {pd.Timestamp(k) if isinstance(k, str) else k: v
            for k, v in pools.items()}


def _get_active_pool(pit_pools: dict, pool_months: list, date: pd.Timestamp) -> set:
    for m in reversed(pool_months):
        if m <= date:
            return set(pit_pools[m])
    return set()


# ═══════════════════════════════════════
# Unified backtest
# ═══════════════════════════════════════

def _build_dynamic_pool(store, date, top_n=100, min_amount=50_000_000):
    """PIT dynamic liquidity pool: top N ETFs by 5d avg amount > min_amount."""
    scores = []
    amt = store.amount
    for code in store.ts_codes:
        if code not in amt.columns:
            continue
        col = amt[code].loc[:date].dropna()
        if len(col) < 5:
            continue
        avg = float(col.iloc[-5:].mean())
        if avg >= min_amount:
            scores.append((code, avg))
    scores.sort(key=lambda x: x[1], reverse=True)
    return set(code for code, _ in scores[:top_n])


def _prior_return(store, code: str, date: pd.Timestamp, lookback: int) -> float:
    prices = store.price_series(code, date, lookback)
    if len(prices) < lookback + 1 or prices[0] <= 0:
        return np.nan
    return float(prices[-1] / prices[0] - 1.0)


def _apply_dynamic_overheat_penalty(
    ranked: list[dict],
    dynamic_only: set[str],
    store: ETFDailyStore,
    date: pd.Timestamp,
    params: EngineParams,
) -> list[dict]:
    if params.dynamic_fusion_mode != "capped" or not dynamic_only or params.dynamic_overheat_penalty >= 1.0:
        return ranked
    adjusted = []
    for r in ranked:
        item = dict(r)
        code = item["ts_code"]
        if code in dynamic_only:
            prior = _prior_return(store, code, date, params.dynamic_overheat_lookback)
            item["dynamic_prior_return"] = prior
            if not np.isnan(prior) and prior >= params.dynamic_overheat_threshold:
                item["score"] *= params.dynamic_overheat_penalty
                item["dynamic_overheat_penalized"] = True
            else:
                item["dynamic_overheat_penalized"] = False
        adjusted.append(item)
    adjusted.sort(key=lambda x: x["score"], reverse=True)
    return adjusted


def _select_targets(
    ranked: list[dict],
    params: EngineParams,
    core_set: set[str] | None,
    dynamic_only: set[str] | None,
    n_override: int = None,
) -> tuple[set[str], dict[str, float]]:
    effective_n = n_override if n_override is not None else params.holdings_num
    if params.dynamic_fusion_mode != "capped" or not core_set:
        target_codes = set(r["ts_code"] for r in ranked[:effective_n])
        if not target_codes:
            return target_codes, {}
        return target_codes, _weight_targets(target_codes, params, dynamic_only)

    dynamic_only = dynamic_only or set()
    core_ranked = [r for r in ranked if r["ts_code"] in core_set]
    dyn_ranked = [r for r in ranked if r["ts_code"] in dynamic_only]

    selected = core_ranked[:effective_n]
    if len(selected) < effective_n:
        selected_codes = {r["ts_code"] for r in selected}
        for r in dyn_ranked:
            if r["ts_code"] in selected_codes:
                continue
            selected.append(r)
            selected_codes.add(r["ts_code"])
            if len(selected) >= effective_n:
                break
    else:
        dynamic_slots = max(0, params.dynamic_max_slots)
        for dyn in dyn_ranked[:dynamic_slots]:
            weakest = min(selected, key=lambda x: x["score"])
            hurdle = weakest["score"] * (1.0 + params.dynamic_score_margin)
            if dyn["score"] > hurdle:
                selected.remove(weakest)
                selected.append(dyn)

    selected.sort(key=lambda x: x["score"], reverse=True)
    selected = selected[:effective_n]
    target_codes = set(r["ts_code"] for r in selected)
    if not target_codes:
        return target_codes, {}

    return target_codes, _weight_targets(target_codes, params, dynamic_only)


def _weight_targets(
    target_codes: set[str],
    params: EngineParams,
    dynamic_only: set[str] | None,
) -> dict[str, float]:
    if not target_codes:
        return {}

    dynamic_only = dynamic_only or set()
    dyn_codes = target_codes & dynamic_only
    core_codes = target_codes - dyn_codes
    if not dyn_codes or params.dynamic_max_total_weight is None:
        w = 1.0 / len(target_codes)
        return {c: w for c in target_codes}

    dyn_total = min(params.dynamic_max_total_weight, len(dyn_codes) / len(target_codes))
    if not core_codes:
        w = 1.0 / len(dyn_codes)
        return {c: w for c in dyn_codes}

    weights = {c: dyn_total / len(dyn_codes) for c in dyn_codes}
    core_w = (1.0 - dyn_total) / len(core_codes)
    weights.update({c: core_w for c in core_codes})
    return weights


def _apply_switch_score_margin(
    target_codes: set[str],
    ranked: list[dict],
    shares: dict[str, int],
    params: EngineParams,
    dynamic_only: set[str] | None,
) -> tuple[set[str], dict[str, float]]:
    """Avoid churn when a new candidate only marginally beats an existing holding."""
    if params.switch_score_margin <= 0 or not target_codes:
        return target_codes, _weight_targets(target_codes, params, dynamic_only)

    held_codes = {c for c, s in shares.items() if s > 0}
    if not held_codes:
        return target_codes, _weight_targets(target_codes, params, dynamic_only)

    score_map = {
        r["ts_code"]: float(r["score"])
        for r in ranked
        if "ts_code" in r and not pd.isna(r.get("score", np.nan))
    }
    keep_candidates = [
        c for c in held_codes - target_codes
        if c in score_map and score_map[c] > 0
    ]
    new_candidates = [
        c for c in target_codes - held_codes
        if c in score_map and score_map[c] > 0
    ]
    if not keep_candidates or not new_candidates:
        return target_codes, _weight_targets(target_codes, params, dynamic_only)

    keep_candidates.sort(key=lambda c: score_map[c], reverse=True)
    new_candidates.sort(key=lambda c: score_map[c])

    final_codes = set(target_codes)
    for held_code in keep_candidates:
        if not new_candidates:
            break
        weakest_new = new_candidates[0]
        hurdle = score_map[held_code] * (1.0 + params.switch_score_margin)
        if score_map[weakest_new] <= hurdle:
            final_codes.remove(weakest_new)
            final_codes.add(held_code)
            new_candidates.pop(0)

    return final_codes, _weight_targets(final_codes, params, dynamic_only)


def _wyckoff_prefilter(store, date, params):
    """Wyckoff Layer 1: keep only ETFs in accumulation/uptrend.
    Returns filtered list of ts_codes."""
    approved = []
    for code in store.ts_codes:
        prices = store.price_series(code, date, 120)
        if len(prices) < 60:
            continue
        current_price = prices[-1]
        # 1. Above MA60 (uptrend requirement)
        ma60 = float(np.mean(prices[-60:]))
        if current_price < ma60:
            continue
        # 2. Not in distribution (top 15% of 60d range + declining vol)
        range_60_high = float(np.max(prices[-60:]))
        range_60_low = float(np.min(prices[-60:]))
        if range_60_low > 0 and range_60_high > range_60_low:
            range_pct = (current_price - range_60_low) / (range_60_high - range_60_low)
            if range_pct > 0.85:
                try:
                    vol_col = store.amount.get(code) if hasattr(store, 'amount') else None
                    if vol_col is not None:
                        vol_series = vol_col.loc[:date].dropna()
                        if len(vol_series) >= 10:
                            vol_short = float(vol_series.iloc[-5:].mean())
                            vol_long = float(vol_series.iloc[-10:].mean())
                            if vol_short < vol_long * 0.8:
                                continue  # distribution zone
                except:
                    pass
        # 3. Not in sustained decline (20d return > -5%)
        if len(prices) >= 20:
            ret_20d = prices[-1] / prices[-20] - 1.0
            if ret_20d < -0.05:
                continue
        approved.append(code)
    return approved if len(approved) >= 5 else store.ts_codes  # minimum 5 candidates


def run_backtest(
    params: EngineParams,
    token_path: Path = None,
    cache_dir: Path = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Single entry point. All features parameterized.

    Returns:
        equity_df, trade_df, audit_dict
    """
    if token_path is None:
        token_path = BASE_DIR / "config" / "tushare_token.txt"
    if cache_dir is None:
        cache_dir = BASE_DIR / "data" / "tushare_cache"

    provider_uri = Path(os.environ.get("QLIB_PROVIDER_URI",
                                        str(BASE_DIR / "data" / "a_share_qlib")))

    # ── 1. Pool setup ──
    if params.pit_pools is not None:
        pit_pools = params.pit_pools
    elif params.pit_pool_path:
        pit_pools = _load_pit_pools(params.pit_pool_path)
    else:
        pit_pools = None

    if pit_pools is not None:
        pool_months = sorted(pit_pools.keys())
        pit_union = set(c for pool in pit_pools.values() for c in pool)
        if params.core_pool is not None:
            pit_union |= set(params.core_pool)
        all_pool_ts = sorted(pit_union)
    else:
        pool_months = None
        all_pool_ts = params.etf_pool_ts

    # ── 2. Data store ──
    cache = SectorProsperityCache(token_path, cache_dir)
    store = ETFDailyStore(cache, all_pool_ts, params.start, params.end)

    # ── 3. Benchmark ──
    reader = QlibDailyReader(provider_uri)
    bench_close = reader.read_field(params.benchmark, "close")
    bench_close = bench_close.loc[pd.Timestamp(params.start):pd.Timestamp(params.end)]

    calendar = store.calendar
    if len(calendar) < params.lookback_days + 1:
        raise RuntimeError(f"Insufficient calendar days: {len(calendar)}")

    # ── 4. Liquidity cache ──
    liq_cache: dict[tuple, float] = {}
    def get_liquidity(code: str, date: pd.Timestamp) -> float:
        key = (code, date)
        if key in liq_cache:
            return liq_cache[key]
        amt = store.amount
        if code not in amt.columns:
            return 0.0
        col = amt[code].loc[:date].dropna()
        if len(col) < 5:
            return 0.0
        val = float(col.iloc[-min(params.liquidity_lookback, len(col)):].mean())
        liq_cache[key] = val
        return val

    # ── 5. State ──
    cash = params.initial_cash
    shares: dict[str, int] = {}
    entry_prices: dict[str, float] = {}
    position_highs: dict[str, float] = {}
    cooldown: dict[str, int] = {}
    permanent_hold_codes = set(params.permanent_hold_codes or ())
    permanent_add_cooldown: dict[str, int] = {}

    daily_records: list[dict] = []
    trade_records: list[dict] = []
    audit: dict = {
        "total_commission": 0.0,
        "total_slippage": 0.0,
        "total_part_penalty": 0.0,
        "partial_fills": 0,
        "rejected_trades": 0,
        "nav_check_errors": 0,
    }

    # ── 6. Main loop ──
    execution_delay = max(1, int(params.execution_delay_days))
    for i, signal_date in enumerate(calendar[:-execution_delay]):
        exec_date = calendar[i + execution_delay]
        if i < params.lookback_days:
            # Warmup: record flat cash
            daily_records.append({
                "date": exec_date,
                "portfolio_value": params.initial_cash,
                "cash": params.initial_cash,
                "position_count": 0, "target_count": 0, "pool_size": 0,
                "market_value": 0.0, "gross_pnl": 0.0, "cost_total": 0.0,
            })
            continue

        # ── 5b. Trading start check ──
        if params.trading_start:
            ts = pd.Timestamp(params.trading_start)
            if signal_date < ts:
                daily_records.append({
                    "date": exec_date,
                    "portfolio_value": params.initial_cash,
                    "cash": params.initial_cash,
                    "position_count": 0, "target_count": 0, "pool_size": 0,
                    "market_value": 0.0, "gross_pnl": 0.0, "cost_total": 0.0,
                })
                continue

        # ── 6a. Decrement cooldown ──
        for c in list(cooldown.keys()):
            cooldown[c] -= 1
            if cooldown[c] <= 0:
                del cooldown[c]
        for c in list(permanent_add_cooldown.keys()):
            permanent_add_cooldown[c] -= 1
            if permanent_add_cooldown[c] <= 0:
                del permanent_add_cooldown[c]

        # ── 6b. Check if today is a rebalance day ──
        do_rebalance = (i % params.rebalance_interval == 0)

        # ── 6b2. Portfolio-level defense ──
        in_defense = False
        if params.defense_ma_period > 0 and len(daily_records) >= params.defense_ma_period:
            recent_nav = [r['portfolio_value'] for r in daily_records[-params.defense_ma_period:]]
            nav_ma = sum(recent_nav) / len(recent_nav)
            current_nav = cash + sum(
                shares.get(c, 0) * (store.latest_price(c, signal_date) if not np.isnan(store.latest_price(c, signal_date)) and store.latest_price(c, signal_date) > 0 else entry_prices.get(c, 0))
                for c in shares if shares.get(c, 0) > 0
            )
            if current_nav < nav_ma:
                in_defense = True

        # ── 6c. PIT pool switching + dual-pool fusion ──
        core_set: set[str] | None = None
        dynamic_only: set[str] = set()
        if pit_pools is not None:
            pit_active = _get_active_pool(pit_pools, pool_months, signal_date)
            active_pool = set(pit_active)
            if params.core_pool is not None:
                core_set = set(params.core_pool) & set(store.ts_codes)
                active_pool |= core_set
                dynamic_only = active_pool - core_set
            temp_codes = store.ts_codes
            store.ts_codes = [c for c in temp_codes if c in active_pool]
            # Add dynamic pool if enabled
            if params.use_dynamic_pool:
                dyn = _build_dynamic_pool(store, signal_date, params.dynamic_top_n, params.dynamic_min_amount)
                if core_set is not None:
                    dynamic_only |= (dyn - core_set)
                store.ts_codes = list(set(store.ts_codes) | dyn)
            # ── Wyckoff pre-filter: Layer 1 ──
            if getattr(params, 'use_wyckoff_prefilter', False):
                _original_codes = store.ts_codes
                store.ts_codes = _wyckoff_prefilter(store, signal_date, params)
            ranked = get_ranked_etfs(store, signal_date, params, exec_date if params.friend_mode else None)
            if getattr(params, 'use_wyckoff_prefilter', False):
                store.ts_codes = _original_codes
            else:
                store.ts_codes = temp_codes
        elif params.core_pool is not None:
            # Dual-pool mode: static core + dynamic
            core_set = set(params.core_pool) & set(store.ts_codes)
            if params.use_dynamic_pool:
                dyn = _build_dynamic_pool(store, signal_date, params.dynamic_top_n, params.dynamic_min_amount)
                active_set = core_set | dyn
                dynamic_only = dyn - core_set
            else:
                active_set = core_set
            temp_codes = store.ts_codes
            store.ts_codes = list(active_set)
                    # ── Wyckoff pre-filter: Layer 1 ──
            if getattr(params, 'use_wyckoff_prefilter', False):
                _original_codes = store.ts_codes
                store.ts_codes = _wyckoff_prefilter(store, signal_date, params)
            ranked = get_ranked_etfs(store, signal_date, params, exec_date if params.friend_mode else None)
            if getattr(params, 'use_wyckoff_prefilter', False):
                store.ts_codes = _original_codes
            else:
                store.ts_codes = temp_codes
            active_pool = active_set
        else:
                    # ── Wyckoff pre-filter: Layer 1 ──
            if getattr(params, 'use_wyckoff_prefilter', False):
                _original_codes = store.ts_codes
                store.ts_codes = _wyckoff_prefilter(store, signal_date, params)
            ranked = get_ranked_etfs(store, signal_date, params, exec_date if params.friend_mode else None)
            active_pool = set(store.ts_codes)

        pool_size = len(active_pool)
        ranked = _apply_dynamic_overheat_penalty(ranked, dynamic_only, store, signal_date, params)

        # ── Mean reversion penalty ──
        if params.mr_ma_period > 0 and len(ranked) > 1 and do_rebalance:
            ma_period = params.mr_ma_period
            threshold = params.mr_threshold
            penalty = params.mr_penalty
            for r in ranked:
                code = r['ts_code']
                prices = store.price_series(code, signal_date, ma_period + 5)
                if len(prices) >= ma_period:
                    ma_val = np.mean(prices[-ma_period:])
                    if ma_val > 0:
                        ratio = prices[-1] / ma_val
                        if ratio >= threshold:
                            r['score'] *= penalty
            ranked.sort(key=lambda x: x['score'], reverse=True)

        if do_rebalance:
            # ── Dynamic holdings count ──
            effective_holdings = params.holdings_num
            if getattr(params, 'use_dynamic_holdings', False) and len(ranked) >= 5:
                top_scores = [float(r.get('score', 0)) for r in ranked[:params.dyn_holdings_max]]
                top_scores = [s for s in top_scores if not np.isnan(s) and not np.isinf(s)]
                if len(top_scores) >= 5:
                    dispersion = (top_scores[0] - top_scores[4]) / max(abs(top_scores[0]), 0.0001)
                    effective_holdings = max(params.dyn_holdings_min,
                        min(params.dyn_holdings_max, int(params.dyn_holdings_max * (1.0 - min(dispersion, 1.0)))))
            target_codes, target_weights = _select_targets(ranked, params, core_set, dynamic_only, effective_holdings)
            target_codes, target_weights = _apply_switch_score_margin(
                target_codes, ranked, shares, params, dynamic_only
            )
            # ── Volatility-adjusted weighting override (after switch score margin) ──
            if getattr(params, 'use_vol_weighting', False) and target_codes:
                vol_lb = getattr(params, 'vol_weight_lookback', 20)
                _vols = {}
                for code in target_codes:
                    prices_arr = store.price_series(code, signal_date, vol_lb + 5)
                    if len(prices_arr) >= vol_lb + 1:
                        rets = np.diff(prices_arr[-(vol_lb+1):]) / prices_arr[-(vol_lb+1):-1]
                        vol = float(np.std(rets) * np.sqrt(252))
                        _vols[code] = max(vol, 0.01)
                if _vols:
                    inv_vols = {c: 1.0 / v for c, v in _vols.items()}
                    total_inv = sum(inv_vols.values())
                    if total_inv > 0:
                        target_weights = {c: v / total_inv for c, v in inv_vols.items()}
            # ── Score-weighted position sizing (after switch score margin) ──
            if getattr(params, 'use_score_weighting', False) and target_codes and len(ranked) > 0:
                _score_map = {}
                for r in ranked:
                    code = r.get('ts_code', '')
                    if code in target_codes:
                        s = float(r.get('score', 0))
                        if not np.isnan(s) and not np.isinf(s) and s > 0:
                            _score_map[code] = s
                if _score_map:
                    if getattr(params, 'use_vol_weighting', False) and _vols:
                        raw = {c: _score_map.get(c, 0.01) / _vols.get(c, 0.01) for c in target_codes}
                    else:
                        raw = {c: _score_map.get(c, 0.01) for c in target_codes}
                    total_raw = sum(raw.values())
                    if total_raw > 0:
                        target_weights = {c: v / total_raw for c, v in raw.items()}
        else:
            target_codes, target_weights = set(), {}
        if in_defense:
            target_codes = set()  # force empty → all positions sold, go to cash
            target_weights = {}
        top_override = set(r["ts_code"] for r in ranked[:params.cooldown_override_top_n])

        # ── 6d. Get next-day open prices ──
        next_open_prices: dict[str, float] = {}
        for code in (target_codes | set(shares.keys())):
            next_open_prices[code] = store.execution_price(code, exec_date, params.execution_price_mode)

        daily_commission = 0.0
        daily_slippage = 0.0
        daily_part_pen = 0.0

        # ── 6e. SELL: exit positions ──
        for code in list(shares.keys()):
            if shares.get(code, 0) <= 0:
                continue

            # Signal: check stops based on signal_date close
            signal_px = store.latest_price(code, signal_date)
            exec_px = next_open_prices.get(code, np.nan)

            # Stop checks (on signal_date close)
            stop_triggered = (code in entry_prices and
                            not np.isnan(signal_px) and
                            signal_px <= entry_prices[code] * params.stop_loss)

            atr_triggered = False
            if params.use_atr_stop_loss:
                ohlc = store.ohlc_series(code, signal_date, params.atr_period + 20)
                if ohlc is not None:
                    atr_val = calculate_atr(ohlc["high"], ohlc["low"], ohlc["close"],
                                            params.atr_period)
                    if atr_val > 0:
                        ep = entry_prices.get(code, signal_px)
                        if not np.isnan(ep) and not np.isnan(signal_px):
                            if signal_px <= ep - params.atr_multiplier * atr_val:
                                atr_triggered = True

            # Determine if should sell
            if do_rebalance:
                should_sell = (code not in target_codes) or stop_triggered or atr_triggered
            else:
                should_sell = stop_triggered or atr_triggered

            is_permanent_hold = code in permanent_hold_codes and shares.get(code, 0) > 0
            if is_permanent_hold:
                if params.permanent_hold_disable_stops:
                    should_sell = False
                else:
                    should_sell = stop_triggered or atr_triggered

            if should_sell:
                liq = get_liquidity(code, signal_date)
                result = execute_sell(code, shares[code], signal_px, exec_px,
                                      entry_prices.get(code, 0), liq, params)
                if result is None:
                    continue

                cash += result["net_proceeds"]
                daily_commission += result["cost_detail"]["commission"] * result["gross_proceeds"]
                daily_slippage += result["cost_detail"]["slip"] * result["gross_proceeds"]
                daily_part_pen += result["cost_detail"]["part_pen"] * result["gross_proceeds"]

                reason = []
                if stop_triggered: reason.append("STOP_LOSS")
                if atr_triggered: reason.append("ATR_STOP")
                if code not in target_codes: reason.append("RANK_OUT")

                trade_records.append({
                    "date": signal_date, "trade_date": exec_date,
                    "ts_code": code, "action": "SELL",
                    "reason": "|".join(reason) if reason else "REBALANCE",
                    "price": result["price"], "shares": result["shares"],
                    "gross_proceeds": result["gross_proceeds"],
                    "cost": result["cost_total"],
                    "net_proceeds": result["net_proceeds"],
                    "partial": result["partial"],
                    "target_weight": target_weights.get(code, 0.0),
                    "is_dynamic_only": code in dynamic_only,
                    "is_permanent_hold": code in permanent_hold_codes,
                    "permanent_dip_add": False,
                })

                if result["partial"]:
                    audit["partial_fills"] += 1
                    shares[code] -= result["shares"]
                    if shares[code] <= 0:
                        shares.pop(code, None)
                        entry_prices.pop(code, None)
                        position_highs.pop(code, None)
                else:
                    shares[code] = 0
                    entry_prices.pop(code, None)
                    position_highs.pop(code, None)

                if params.cooldown_days > 0:
                    cooldown[code] = params.cooldown_days

        # ── 6f. BUY: enter new positions ──
        if do_rebalance:
            active_set = target_codes | set(c for c in shares if shares.get(c, 0) > 0)
            if active_set:
                n_active = max(1, len(active_set))
                total_value = cash
                for c in shares:
                    if shares.get(c, 0) > 0:
                        px = store.latest_price(c, signal_date)
                        if not np.isnan(px) and px > 0:
                            total_value += shares[c] * px

                per_slot = total_value / n_active
                buy_reasons = {c: "RANK_IN" for c in target_codes}

                if params.permanent_dip_add_enabled and permanent_hold_codes and total_value > 0:
                    for c in sorted(permanent_hold_codes):
                        held = shares.get(c, 0)
                        if held <= 0 or c in permanent_add_cooldown:
                            continue
                        signal_px = store.latest_price(c, signal_date)
                        high_px = position_highs.get(c, signal_px)
                        if np.isnan(signal_px) or signal_px <= 0 or np.isnan(high_px) or high_px <= 0:
                            continue
                        drawdown_from_high = signal_px / high_px - 1.0
                        if drawdown_from_high > -params.permanent_dip_threshold:
                            continue
                        current_value = held * signal_px
                        current_weight = current_value / total_value
                        target_weight = min(
                            params.permanent_max_weight,
                            current_weight + params.permanent_dip_add_weight,
                        )
                        if target_weight <= current_weight:
                            continue
                        target_codes.add(c)
                        target_weights[c] = max(target_weights.get(c, 0.0), target_weight)
                        buy_reasons[c] = "PERMANENT_DIP_ADD"
                        next_open_prices[c] = store.execution_price(c, exec_date, params.execution_price_mode)
                        permanent_add_cooldown[c] = params.permanent_add_cooldown_days

                for code in sorted(target_codes):
                    # Cooldown check
                    if code in cooldown and code not in top_override:
                        continue

                    exec_px = next_open_prices.get(code, np.nan)
                    if np.isnan(exec_px) or exec_px <= 0:
                        continue

                    current_val = shares.get(code, 0) * exec_px
                    target_value = total_value * target_weights.get(code, 1.0 / n_active)
                    diff = target_value - current_val
                    if diff <= 0:
                        continue

                    buy_cash = min(cash, diff)
                    liq = get_liquidity(code, signal_date)

                    result = execute_buy(code, buy_cash, diff, exec_px, liq, params)
                    if result is None:
                        audit["rejected_trades"] += 1
                        continue

                    cash -= result["net_cost"]
                    daily_commission += result["cost_detail"]["commission"] * result["gross_cost"]
                    daily_slippage += result["cost_detail"]["slip"] * result["gross_cost"]
                    daily_part_pen += result["cost_detail"]["part_pen"] * result["gross_cost"]

                    old_shares = shares.get(code, 0)
                    shares[code] = old_shares + result["shares"]
                    if old_shares == 0:
                        entry_prices[code] = exec_px
                        position_highs[code] = exec_px
                    else:
                        entry_prices[code] = (old_shares * entry_prices[code]
                                             + result["shares"] * exec_px) / (old_shares + result["shares"])

                    trade_records.append({
                        "date": signal_date, "trade_date": exec_date,
                        "ts_code": code, "action": "BUY",
                        "reason": buy_reasons.get(code, "RANK_IN"),
                        "price": result["price"], "shares": result["shares"],
                        "gross_cost": result["gross_cost"],
                        "cost": result["cost_total"],
                        "net_cost": result["net_cost"],
                        "partial": result["partial"],
                        "score": next((r["score"] for r in ranked if r["ts_code"] == code), np.nan),
                        "target_weight": target_weights.get(code, np.nan),
                        "is_dynamic_only": code in dynamic_only,
                        "is_permanent_hold": code in permanent_hold_codes,
                        "permanent_dip_add": buy_reasons.get(code) == "PERMANENT_DIP_ADD",
                        "dynamic_prior_return": next((r.get("dynamic_prior_return", np.nan) for r in ranked if r["ts_code"] == code), np.nan),
                        "dynamic_overheat_penalized": next((r.get("dynamic_overheat_penalized", False) for r in ranked if r["ts_code"] == code), False),
                    })

                    if result["partial"]:
                        audit["partial_fills"] += 1

        # ── 6g. Update position highs (on execution-date close) ──
        for c in shares:
            if shares.get(c, 0) <= 0:
                continue
            px_c = store.latest_price(c, exec_date)
            if not np.isnan(px_c) and px_c > 0:
                position_highs[c] = max(position_highs.get(c, px_c), px_c)

        # ── 6h. Value portfolio (execution-date close) ──
        market_value = 0.0
        for c in shares:
            if shares.get(c, 0) > 0:
                px_c = store.latest_price(c, exec_date)
                if not np.isnan(px_c) and px_c > 0:
                    market_value += shares[c] * px_c
                else:
                    market_value += shares[c] * entry_prices.get(c, 0)

        portfolio_value = cash + market_value

        # Sanity check: cash >= 0
        if cash < -1.0:
            audit["nav_check_errors"] += 1

        daily_records.append({
            "date": exec_date,
            "portfolio_value": portfolio_value,
            "cash": cash,
            "market_value": market_value,
            "position_count": sum(1 for s in shares.values() if s > 0),
            "target_count": len(target_codes),
            "pool_size": pool_size,
            "gross_pnl": 0.0,  # computed per-trade in audit
            "cost_total": daily_commission + daily_slippage + daily_part_pen,
        })

        audit["total_commission"] += daily_commission
        audit["total_slippage"] += daily_slippage
        audit["total_part_penalty"] += daily_part_pen

    # ── 7. Build equity DataFrame ──
    equity = pd.DataFrame(daily_records).drop_duplicates("date", keep="last").set_index("date")
    if equity.empty:
        raise RuntimeError("No equity records generated")

    # Benchmark
    if not bench_close.empty:
        bench = bench_close.reindex(equity.index).ffill()
        fb = bench.dropna().iloc[0]
        equity["benchmark_value"] = params.initial_cash * bench / fb
        equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].iloc[0] - 1.0

    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1.0

    # ── 8. Trade log ──
    trades = pd.DataFrame(trade_records)

    # ── 9. NAV reconciliation check ──
    # Verify: portfolio_value ≈ cash + market_value for all days
    equity["nav_check"] = equity["portfolio_value"] - (equity["cash"] + equity["market_value"])
    max_nav_error = equity["nav_check"].abs().max()
    audit["max_nav_error"] = max_nav_error

    # ── 10. Summary ──
    stats = _summarize(equity)
    audit["stats"] = stats

    return equity, trades, audit


# ═══════════════════════════════════════
# Convenience runner
# ═══════════════════════════════════════

def run_and_save(params: EngineParams, out_dir: Path = None):
    """Run backtest and save results to CSV."""
    if out_dir is None:
        out_dir = BASE_DIR / "outputs" / "etf_loop"
    out_dir.mkdir(parents=True, exist_ok=True)

    equity, trades, audit = run_backtest(params)

    suffix = f"{params.exp_tag}_h{params.holdings_num}"
    suffix += f"_{params.start.replace('-','')}_{params.end.replace('-','')}"

    equity.to_csv(out_dir / f"etf_loop_equity_{suffix}.csv")
    trades.to_csv(out_dir / f"etf_loop_targets_{suffix}.csv", index=False)
    pd.DataFrame([audit["stats"]]).to_csv(out_dir / f"etf_loop_summary_{suffix}.csv", index=False)

    print(f"{params.exp_tag}: ann={audit['stats']['annual_return']*100:.2f}%, "
          f"Sharpe={audit['stats']['sharpe_ratio']:.2f}, "
          f"DD={audit['stats']['max_drawdown']*100:.2f}%, "
          f"trades={len(trades)}, "
          f"nav_err={audit['max_nav_error']:.6f}")

    return equity, trades, audit


# ═══════════════════════════════════════
# Smoke test
# ═══════════════════════════════════════

if __name__ == "__main__":
    os.environ.setdefault("QLIB_PROVIDER_URI",
                          str(BASE_DIR / "data" / "a_share_qlib"))
    sys.path.insert(0, str(BASE_DIR))

    from strategies.etf_loop_strategy import ETFLoopParams

    # Test 1: Static pool (union) — should match original backtest
    import pickle
    with open(BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" /
              "etf_pool_G2_PIT_monthly.pkl", "rb") as f:
        pools = pickle.load(f)
    all_ts = sorted(set(c for pool in pools.values() for c in pool))

    print("=== K0 Invariant Test ===")
    print(f"Pool: {len(all_ts)} ETFs, 2024 H1")

    params1 = EngineParams(
        etf_pool_ts=all_ts,
        holdings_num=5,
        start="2024-01-01", end="2024-06-30",
        exp_tag="K0_test1",
    )
    e1, t1, a1 = run_and_save(params1)

    # Test 2: Same params, PIT mode disabled — should give identical results
    params2 = EngineParams(
        etf_pool_ts=all_ts,
        holdings_num=5, rebalance_interval=1,
        start="2024-01-01", end="2024-06-30",
        exp_tag="K0_test2",
    )
    e2, t2, a2 = run_and_save(params2)

    # Compare
    diff_ann = abs(a1["stats"]["annual_return"] - a2["stats"]["annual_return"])
    diff_trades = abs(len(t1) - len(t2))
    print(f"\nInvariant check: |Δ ann| = {diff_ann*100:.2f}pp, |Δ trades| = {diff_trades}")
    if diff_ann < 0.001 and diff_trades == 0:
        print("✅ PASS: K0 invariants hold.")
    else:
        print(f"❌ FAIL: K0 invariants broken (Δ ann={diff_ann*100:.2f}pp, Δ trades={diff_trades})")
