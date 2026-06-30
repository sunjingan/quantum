#!/usr/bin/env python3
"""Export ETF Loop candidates as standalone JoinQuant scripts."""
from __future__ import annotations

import pickle
import textwrap
from pathlib import Path
from pprint import pformat

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "tushare_cache" / "sector_prosperity"
OUT = ROOT / "joinquant_strategies" / "etf_loop"


def ts_to_jq(code: str) -> str:
    symbol, exchange = str(code).split(".")
    if exchange == "SH":
        return f"{symbol}.XSHG"
    if exchange == "SZ":
        return f"{symbol}.XSHE"
    raise ValueError(code)


def load_f2_pool() -> list[str]:
    df = pd.read_csv(CACHE / "etf_pool_F2_v3.csv", dtype={"ts_code": str})
    return sorted(ts_to_jq(c) for c in df["ts_code"].astype(str).tolist())


def load_pit_pools() -> dict[str, list[str]]:
    with open(CACHE / "etf_pool_G2_PIT_monthly.pkl", "rb") as f:
        pools = pickle.load(f)
    out: dict[str, list[str]] = {}
    for k, values in pools.items():
        month = pd.Timestamp(k).strftime("%Y-%m")
        out[month] = sorted(ts_to_jq(c) for c in values)
    return dict(sorted(out.items()))


MANUAL_202606 = [
    "588000.XSHG",  # 科创50
    "159995.XSHE",  # 芯片
    "515070.XSHG",  # 人工智能
    "562500.XSHG",  # 机器人
    "512880.XSHG",  # 证券
    "512890.XSHG",  # 红利低波
    "159928.XSHE",  # 消费
    "159941.XSHE",  # 纳指100
    "518880.XSHG",  # 黄金
    "159930.XSHE",  # 能源
]


FIXED10_POOL = [
    "588000.XSHG",
    "159995.XSHE",
    "515070.XSHG",
    "562500.XSHG",
    "512880.XSHG",
    "512890.XSHG",
    "159928.XSHE",
    "159941.XSHE",
    "518880.XSHG",
    "159930.XSHE",
]


COMMON = r'''
import math
import numpy as np
import pandas as pd


def setup_platform():
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    # JoinQuant PriceRelatedSlippage is a bid/ask spread; 0.0004 means 2bp per side.
    # Our default candidate cost: commission 1.5bp + slippage 2bp per side.
    try:
        set_slippage(PriceRelatedSlippage(0.0004))
    except Exception:
        set_slippage(FixedSlippage(0.001))
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0,
        open_commission=0.00015,
        close_commission=0.00015,
        close_today_commission=0,
        min_commission=1,
    ), type='fund')
    log.set_level('system', 'error')


def safe_history(code, count, fields):
    try:
        df = attribute_history(code, count, '1d', fields, skip_paused=True, df=True)
    except Exception as exc:
        log.warn('history failed %s %s' % (code, exc))
        return pd.DataFrame()
    return df.dropna()


def calc_rsi(prices, period=6):
    prices = np.asarray(prices, dtype=float)
    if len(prices) < period + 1:
        return np.array([])
    delta = np.diff(prices)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    out = []
    for i in range(period, len(delta) + 1):
        avg_gain = np.mean(gain[i-period:i])
        avg_loss = np.mean(loss[i-period:i])
        if avg_loss == 0:
            out.append(100.0)
        else:
            rs = avg_gain / avg_loss
            out.append(100.0 - 100.0 / (1.0 + rs))
    return np.asarray(out)


def calc_atr_from_df(df, period=14):
    if df is None or df.empty or len(df) < period + 1:
        return np.nan
    high = np.asarray(df['high'], dtype=float)
    low = np.asarray(df['low'], dtype=float)
    close = np.asarray(df['close'], dtype=float)
    trs = []
    for i in range(1, len(close)):
        trs.append(max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1])))
    if len(trs) < period:
        return np.nan
    return float(np.mean(trs[-period:]))


def annualized_regression_score(prices):
    prices = np.asarray(prices, dtype=float)
    prices = prices[np.isfinite(prices)]
    if len(prices) < 5 or np.any(prices <= 0):
        return np.nan, np.nan, 0.0
    y = np.log(prices)
    x = np.arange(len(y))
    weights = np.linspace(1, 2, len(y))
    slope, intercept = np.polyfit(x, y, 1, w=weights)
    ann = math.exp(slope * 250) - 1.0
    ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
    ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    return ann, r2, ann * r2


def annualized_return(prices, lookback):
    prices = np.asarray(prices, dtype=float)
    if len(prices) < lookback + 1 or prices[-lookback-1] <= 0:
        return np.nan
    ret = prices[-1] / prices[-lookback-1] - 1.0
    return (1.0 + ret) ** (250.0 / lookback) - 1.0


def has_recent_large_drop(prices, loss=0.97):
    prices = np.asarray(prices, dtype=float)
    if len(prices) < 4:
        return True
    con1 = min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < loss
    con2 = (prices[-1] < prices[-2] < prices[-3] < prices[-4]) and (prices[-1] / prices[-4] < loss)
    con3 = False
    if len(prices) >= 6:
        con3 = (prices[-2] < prices[-3] < prices[-4] < prices[-5]) and (prices[-2] / prices[-5] < loss)
    return bool(con1 or con2 or con3)


def volume_ratio_filter(code, date, prices, volume_lookback=5, threshold=2.0, return_limit=1.0):
    df = safe_history(code, volume_lookback + 1, ['volume'])
    if df.empty or len(df) < volume_lookback + 1:
        return False
    recent = float(df['volume'].iloc[-1])
    base = float(df['volume'].iloc[-volume_lookback-1:-1].mean())
    if base <= 0:
        return False
    ann = annualized_return(prices, 25)
    return recent / base > threshold and np.isfinite(ann) and ann > return_limit


def score_one_etf(code, lookback_days=25, max_score=500.0, ma_penalty=True):
    hist_count = max(lookback_days, 60, 25, 14 + 20) + 25
    df = safe_history(code, hist_count, ['close', 'high', 'low', 'volume'])
    if df.empty or len(df) < lookback_days + 1:
        return None
    prices = np.asarray(df['close'], dtype=float)
    if len(prices) < lookback_days + 1 or np.any(prices[-(lookback_days+1):] <= 0):
        return None

    if volume_ratio_filter(code, None, prices):
        return None

    rsi_vals = calc_rsi(prices, 6)
    if len(rsi_vals) >= 1:
        ma5 = np.mean(prices[-5:]) if len(prices) >= 5 else np.nan
        if rsi_vals[-1] > 98 and (not np.isfinite(ma5) or prices[-1] < ma5):
            return None

    if len(prices) >= 11:
        short_ret = prices[-1] / prices[-11] - 1.0
        short_ann = (1.0 + short_ret) ** 25.0 - 1.0
        if short_ann < 0:
            return None

    recent = prices[-(lookback_days + 1):]
    ann, r2, score = annualized_regression_score(recent)

    if ma_penalty and len(prices) >= 60:
        ma60 = float(np.mean(prices[-60:]))
        if ma60 > 0 and prices[-1] / ma60 >= 1.14:
            score *= 0.5

    if has_recent_large_drop(prices, 0.97):
        score = 0.0

    if score <= 0 or score > max_score:
        return None
    return {
        'code': code,
        'score': float(score),
        'annualized_returns': float(ann),
        'r2': float(r2),
    }


def get_active_dynamic_pool(context):
    month = context.previous_date.strftime('%Y-%m')
    active = set()
    for m in sorted(g.dynamic_pit_pools.keys(), reverse=True):
        if m <= month:
            active = set(g.dynamic_pit_pools[m])
            break
    if getattr(g, 'use_manual_current_month_pool', False) and month == g.manual_pool_month:
        active |= set(g.manual_dynamic_pool)
    return active


def rank_candidates(context):
    core_set = set(g.core_pool)
    dynamic_pool = get_active_dynamic_pool(context)
    active_pool = sorted(core_set | dynamic_pool)
    dynamic_only = set(active_pool) - core_set
    rows = []
    for code in active_pool:
        row = score_one_etf(code, g.lookback_days, g.max_score_threshold, ma_penalty=True)
        if row is None:
            continue
        if code in dynamic_only:
            hist = safe_history(code, g.dynamic_overheat_lookback + 1, ['close'])
            if not hist.empty and len(hist) >= g.dynamic_overheat_lookback + 1:
                prior = float(hist['close'].iloc[-1] / hist['close'].iloc[-g.dynamic_overheat_lookback-1] - 1.0)
                row['dynamic_prior_return'] = prior
                if prior >= g.dynamic_overheat_threshold:
                    row['score'] *= g.dynamic_overheat_penalty
                    row['dynamic_overheat_penalized'] = True
                else:
                    row['dynamic_overheat_penalized'] = False
        row['is_dynamic_only'] = code in dynamic_only
        rows.append(row)
    rows.sort(key=lambda x: x['score'], reverse=True)
    return rows, core_set, dynamic_only


def select_capped_targets(ranked, core_set, dynamic_only, target_num):
    if target_num <= 0:
        return [], {}
    core_ranked = [r for r in ranked if r['code'] in core_set]
    dyn_ranked = [r for r in ranked if r['code'] in dynamic_only]
    selected = core_ranked[:target_num]
    if len(selected) < target_num:
        selected_codes = set(r['code'] for r in selected)
        for r in dyn_ranked:
            if r['code'] not in selected_codes:
                selected.append(r)
                selected_codes.add(r['code'])
            if len(selected) >= target_num:
                break
    else:
        for dyn in dyn_ranked[:g.dynamic_max_slots]:
            weakest = min(selected, key=lambda x: x['score'])
            if dyn['score'] > weakest['score'] * (1.0 + g.dynamic_score_margin):
                selected.remove(weakest)
                selected.append(dyn)
    selected.sort(key=lambda x: x['score'], reverse=True)
    selected = selected[:target_num]
    codes = [r['code'] for r in selected]
    if not codes:
        return [], {}
    dyn_codes = [c for c in codes if c in dynamic_only]
    core_codes = [c for c in codes if c not in dynamic_only]
    if dyn_codes and core_codes:
        dyn_total = min(g.dynamic_max_total_weight, len(dyn_codes) / float(len(codes)))
        weights = dict((c, dyn_total / len(dyn_codes)) for c in dyn_codes)
        weights.update(dict((c, (1.0 - dyn_total) / len(core_codes)) for c in core_codes))
    else:
        weights = dict((c, 1.0 / len(codes)) for c in codes)
    return codes, weights


def calc_adaptive_target(context):
    if not getattr(g, 'use_adaptive', False):
        return int(g.holdings_num), 1.0
    df = safe_history('000300.XSHG', g.adaptive_window + 1, ['close'])
    if df.empty or len(df) < g.adaptive_window + 1:
        return int(g.holdings_num), 1.0
    ret = float(df['close'].iloc[-1] / df['close'].iloc[-g.adaptive_window-1] - 1.0)
    target_num = g.adaptive_tiers_n[-1]
    target_exposure = g.adaptive_tiers_exposure[-1]
    for i, threshold in enumerate(g.adaptive_tiers_ret):
        if ret >= threshold:
            target_num = g.adaptive_tiers_n[i]
            target_exposure = g.adaptive_tiers_exposure[i]
            break
    log.info('[%s] HS300 %sd ret %.2f%% -> target holdings %s exposure %.2f' % (
        g.strategy_name, g.adaptive_window, ret * 100, target_num, target_exposure
    ))
    return int(target_num), float(target_exposure)


def should_stop_position(context, code):
    pos = context.portfolio.positions[code]
    if pos.total_amount <= 0:
        return False
    df = safe_history(code, 40, ['close', 'high', 'low'])
    if df.empty or len(df) < 15:
        return False
    prev_close = float(df['close'].iloc[-1])
    avg_cost = float(pos.avg_cost)
    if avg_cost > 0 and prev_close <= avg_cost * 0.95:
        return True
    atr = calc_atr_from_df(df, 14)
    if np.isfinite(atr) and avg_cost > 0 and prev_close <= avg_cost - 2.0 * atr:
        return True
    return False


def execute_targets(context, target_codes, target_weights, label):
    target_set = set(target_codes)
    hold_list = list(context.portfolio.positions.keys())

    for code in hold_list:
        pos = context.portfolio.positions[code]
        if pos.total_amount <= 0:
            continue
        if code not in target_set or should_stop_position(context, code):
            order_target_value(code, 0)
            log.info('[%s] SELL %s %s' % (label, code, get_security_info(code).display_name))

    portfolio_value = context.portfolio.total_value
    current_hold = set([c for c, p in context.portfolio.positions.items() if p.total_amount > 0])
    for code in target_codes:
        if code in current_hold and not getattr(g, 'rebalance_existing', False):
            continue
        target_value = portfolio_value * target_weights.get(code, 0.0)
        if target_value > 0:
            order_target_value(code, target_value)
            log.info('[%s] BUY/TARGET %s %s target_value=%.2f' % (
                label, code, get_security_info(code).display_name, target_value
            ))
'''


def daily_strategy(
    name: str,
    f2_pool: list[str],
    pit_pools: dict[str, list[str]],
    *,
    adaptive_tiers_ret: list[float] | None = None,
    adaptive_tiers_n: list[int] | None = None,
    adaptive_tiers_exposure: list[float] | None = None,
    adaptive_window: int = 15,
) -> str:
    use_adaptive = adaptive_tiers_ret is not None
    if adaptive_tiers_ret is None:
        adaptive_tiers_ret = []
    if adaptive_tiers_n is None:
        adaptive_tiers_n = []
    if adaptive_tiers_exposure is None:
        adaptive_tiers_exposure = [1.0] * len(adaptive_tiers_n)
    if use_adaptive and not (
        len(adaptive_tiers_n) == len(adaptive_tiers_ret) + 1
        and len(adaptive_tiers_exposure) == len(adaptive_tiers_n)
    ):
        raise ValueError(f"bad adaptive tier lengths for {name}")
    core_pool_repr = pformat(f2_pool, width=120, sort_dicts=False)
    pit_pool_repr = pformat(pit_pools, width=120, sort_dicts=False)
    manual_pool_repr = pformat(MANUAL_202606, width=120, sort_dicts=False)
    body = f"""
# Auto-generated from local ETF Loop research repo.
# Strategy: {name}
# JoinQuant account name suggestion: {name}_paper

{COMMON}


CORE_POOL = {core_pool_repr}
DYNAMIC_PIT_POOLS = {pit_pool_repr}
MANUAL_DYNAMIC_POOL_202606 = {manual_pool_repr}


def initialize(context):
    setup_platform()
    g.strategy_name = '{name}'
    g.account_name = '{name}_paper'
    g.core_pool = CORE_POOL
    g.dynamic_pit_pools = DYNAMIC_PIT_POOLS
    g.manual_dynamic_pool = MANUAL_DYNAMIC_POOL_202606
    g.manual_pool_month = '2026-06'
    g.use_manual_current_month_pool = True

    g.holdings_num = 5
    g.lookback_days = 25
    g.max_score_threshold = 500.0
    g.dynamic_max_slots = 1
    g.dynamic_max_total_weight = 0.10
    g.dynamic_score_margin = 0.05
    g.dynamic_overheat_lookback = 20
    g.dynamic_overheat_threshold = 0.10
    g.dynamic_overheat_penalty = 0.50
    g.rebalance_existing = False

    g.use_adaptive = {repr(use_adaptive)}
    g.adaptive_window = {repr(adaptive_window)}
    g.adaptive_tiers_ret = {repr(adaptive_tiers_ret)}
    g.adaptive_tiers_n = {repr(adaptive_tiers_n)}
    g.adaptive_tiers_exposure = {repr(adaptive_tiers_exposure)}

    run_daily(trade, '09:35')


def trade(context):
    target_num, target_exposure = calc_adaptive_target(context)
    ranked, core_set, dynamic_only = rank_candidates(context)
    target_codes, target_weights = select_capped_targets(ranked, core_set, dynamic_only, target_num)
    target_weights = dict((code, weight * target_exposure) for code, weight in target_weights.items())
    log.info('[%s] previous_date=%s exposure=%.2f targets=%s' % (
        g.strategy_name, context.previous_date, target_exposure, target_codes
    ))
    execute_targets(context, target_codes, target_weights, g.strategy_name)
"""
    return textwrap.dedent(body).strip() + "\n"


def current_month_daily_strategy(
    name: str,
    f2_pool: list[str],
    current_dynamic_pool: list[str],
    *,
    adaptive_tiers_ret: list[float] | None = None,
    adaptive_tiers_n: list[int] | None = None,
    adaptive_tiers_exposure: list[float] | None = None,
    adaptive_window: int = 15,
) -> str:
    """Short JoinQuant script for paper trading with only the current dynamic pool.

    This version is intentionally not suitable for long historical PIT backtests.
    It is meant for JoinQuant paper-trading admission when the platform editor
    cannot comfortably accept the full embedded historical PIT dictionary.
    """
    use_adaptive = adaptive_tiers_ret is not None
    if adaptive_tiers_ret is None:
        adaptive_tiers_ret = []
    if adaptive_tiers_n is None:
        adaptive_tiers_n = []
    if adaptive_tiers_exposure is None:
        adaptive_tiers_exposure = [1.0] * len(adaptive_tiers_n)
    if use_adaptive and not (
        len(adaptive_tiers_n) == len(adaptive_tiers_ret) + 1
        and len(adaptive_tiers_exposure) == len(adaptive_tiers_n)
    ):
        raise ValueError(f"bad adaptive tier lengths for {name}")

    core_pool_repr = pformat(f2_pool, width=120, sort_dicts=False)
    current_pool_repr = pformat(current_dynamic_pool, width=120, sort_dicts=False)
    body = f"""
# Auto-generated from local ETF Loop research repo.
# Strategy: {name}_current_month
# JoinQuant account name suggestion: {name}_current_month_paper
# This compact script hard-codes only the current dynamic pool. Do not use it
# to interpret long historical PIT backtests.

{COMMON}


CORE_POOL = {core_pool_repr}
CURRENT_DYNAMIC_POOL = {current_pool_repr}


def initialize(context):
    setup_platform()
    g.strategy_name = '{name}_current_month'
    g.account_name = '{name}_current_month_paper'
    g.core_pool = CORE_POOL
    # Keep the current pool active from 2026-06 onward; update this monthly.
    g.dynamic_pit_pools = {{'2026-06': CURRENT_DYNAMIC_POOL}}
    g.manual_dynamic_pool = []
    g.manual_pool_month = '2026-06'
    g.use_manual_current_month_pool = False

    g.holdings_num = 5
    g.lookback_days = 25
    g.max_score_threshold = 500.0
    g.dynamic_max_slots = 1
    g.dynamic_max_total_weight = 0.10
    g.dynamic_score_margin = 0.05
    g.dynamic_overheat_lookback = 20
    g.dynamic_overheat_threshold = 0.10
    g.dynamic_overheat_penalty = 0.50
    g.rebalance_existing = False

    g.use_adaptive = {repr(use_adaptive)}
    g.adaptive_window = {repr(adaptive_window)}
    g.adaptive_tiers_ret = {repr(adaptive_tiers_ret)}
    g.adaptive_tiers_n = {repr(adaptive_tiers_n)}
    g.adaptive_tiers_exposure = {repr(adaptive_tiers_exposure)}

    run_daily(trade, '09:35')


def trade(context):
    target_num, target_exposure = calc_adaptive_target(context)
    ranked, core_set, dynamic_only = rank_candidates(context)
    target_codes, target_weights = select_capped_targets(ranked, core_set, dynamic_only, target_num)
    target_weights = dict((code, weight * target_exposure) for code, weight in target_weights.items())
    log.info('[%s] previous_date=%s exposure=%.2f targets=%s' % (
        g.strategy_name, context.previous_date, target_exposure, target_codes
    ))
    execute_targets(context, target_codes, target_weights, g.strategy_name)
"""
    return textwrap.dedent(body).strip() + "\n"


def fixed_pool_widea_strategy(name: str, fixed_pool: list[str]) -> str:
    """Compact JoinQuant WideA script with a fixed ETF universe and no dynamic pool."""
    pool_repr = pformat(fixed_pool, width=120, sort_dicts=False)
    body = f"""
# Auto-generated from local ETF Loop research repo.
# Strategy: {name}
# JoinQuant account name suggestion: {name}_paper
# Fixed ETF pool only: no PIT dynamic pool, no minute execution pressure layer.

{COMMON}


CORE_POOL = {pool_repr}


def initialize(context):
    setup_platform()
    g.strategy_name = '{name}'
    g.account_name = '{name}_paper'
    g.core_pool = CORE_POOL
    g.dynamic_pit_pools = {{}}
    g.manual_dynamic_pool = []
    g.manual_pool_month = ''
    g.use_manual_current_month_pool = False

    g.holdings_num = 5
    g.lookback_days = 25
    g.max_score_threshold = 500.0
    # These dynamic-pool parameters are inert because dynamic_pit_pools is empty.
    g.dynamic_max_slots = 0
    g.dynamic_max_total_weight = 0.0
    g.dynamic_score_margin = 0.05
    g.dynamic_overheat_lookback = 20
    g.dynamic_overheat_threshold = 0.10
    g.dynamic_overheat_penalty = 0.50
    g.rebalance_existing = False

    # WideA adaptive holdings: HS300 15d return -> target holdings, exposure always 100% except cash tier.
    g.use_adaptive = True
    g.adaptive_window = 15
    g.adaptive_tiers_ret = [0.06, 0.03, 0.0, -0.02, -0.05, -0.08]
    g.adaptive_tiers_n = [5, 5, 4, 3, 2, 1, 0]
    g.adaptive_tiers_exposure = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0]

    run_daily(trade, '09:35')


def trade(context):
    target_num, target_exposure = calc_adaptive_target(context)
    ranked, core_set, dynamic_only = rank_candidates(context)
    target_codes, target_weights = select_capped_targets(ranked, core_set, dynamic_only, target_num)
    target_weights = dict((code, weight * target_exposure) for code, weight in target_weights.items())
    log.info('[%s] previous_date=%s exposure=%.2f targets=%s' % (
        g.strategy_name, context.previous_date, target_exposure, target_codes
    ))
    execute_targets(context, target_codes, target_weights, g.strategy_name)
"""
    return textwrap.dedent(body).strip() + "\n"


FRIEND_COMMON = r'''
import math
import numpy as np
import pandas as pd
import talib


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    set_slippage(FixedSlippage(0.001))
    set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.0002,
                             close_commission=0.0002, close_today_commission=0,
                             min_commission=1), type='fund')
    log.set_level('system', 'error')
    g.strategy_name = 'friend9'
    g.account_name = 'friend9_paper'
    g.etf_pool = FRIEND_POOL_9
    g.target_num = 1
    g.auto_day = True
    g.min_days = 20
    g.max_days = 60
    g.ratio_cap = 0.9
    run_daily(trade, '9:50')


def safe_history(code, count, fields):
    try:
        return attribute_history(code, count, '1d', fields)
    except Exception as exc:
        log.warn('history failed %s %s' % (code, exc))
        return pd.DataFrame()


def has_large_recent_drop(prices):
    if len(prices) < 5:
        return True
    con1 = min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < 0.95
    con2 = (prices[-1] < prices[-2] < prices[-3] < prices[-4]) and (prices[-1] / prices[-4] < 0.95)
    con3 = (prices[-2] < prices[-3] < prices[-4] < prices[-5]) and (prices[-2] / prices[-5] < 0.95)
    return bool(con1 or con2 or con3)


def get_etf_premium_rate_real(context, etf_code):
    try:
        etf_price = get_price(etf_code, start_date=context.previous_date, end_date=context.previous_date).iloc[-1]['close']
        iopv = get_extras('unit_net_value', etf_code, start_date=context.previous_date,
                          end_date=context.previous_date).iloc[-1].values[0]
        if iopv is not None and iopv != 0:
            return (etf_price - iopv) / iopv * 100.0
    except Exception:
        pass
    return 0.0


def rank_friend9_simple(context):
    data = []
    current_data = get_current_data()
    for etf in g.etf_pool:
        df = safe_history(etf, g.m_days, ['close', 'high'])
        if len(df) < g.m_days:
            continue
        last_price = current_data[etf].last_price
        if last_price is None or last_price <= 0:
            continue
        prices = np.append(df['close'].values, last_price)
        y = np.log(prices)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))
        slope, intercept = np.polyfit(x, y, 1, w=weights)
        annualized_returns = math.exp(slope * 250) - 1
        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
        ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot else 0
        score = annualized_returns * r2
        if min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < 0.95:
            score = 0.0
        if 0 < score < 6:
            data.append({'code': etf, 'score': float(score)})
    data.sort(key=lambda x: x['score'], reverse=True)
    return [x['code'] for x in data]


def rank_friend9_auto(context):
    data = []
    current_data = get_current_data()
    for etf in g.etf_pool:
        df = safe_history(etf, g.max_days + 10, ['close', 'high', 'low'])
        if (
            len(df) < (g.max_days + 10)
            or df['low'].isna().sum() > g.max_days
            or df['close'].isna().sum() > g.max_days
            or df['high'].isna().sum() > g.max_days
        ):
            continue
        long_atr = talib.ATR(df['high'], df['low'], df['close'], timeperiod=g.max_days)
        short_atr = talib.ATR(df['high'], df['low'], df['close'], timeperiod=g.min_days)
        long_val = float(long_atr[-1])
        short_val = float(short_atr[-1])
        if not np.isfinite(long_val) or long_val <= 0 or not np.isfinite(short_val):
            continue
        lookback = int(g.min_days + (g.max_days - g.min_days) * (1 - min(g.ratio_cap, short_val / long_val)))
        last_price = current_data[etf].last_price
        if last_price is None or last_price <= 0:
            continue
        prices = np.append(df['close'].values, last_price)
        prices = prices[-lookback:]
        if len(prices) < 5 or np.any(pd.isna(prices)) or np.any(prices <= 0):
            continue
        y = np.log(prices)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))
        slope, intercept = np.polyfit(x, y, 1, w=weights)
        annualized_returns = math.exp(slope * 250) - 1
        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
        ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot else 0
        score = annualized_returns * r2
        if has_large_recent_drop(prices):
            score = 0.0
        if get_etf_premium_rate_real(context, etf) >= 5:
            score -= 1.0
        if 0 < score < 6:
            data.append({'code': etf, 'score': float(score)})
    data.sort(key=lambda x: x['score'], reverse=True)
    return [x['code'] for x in data]


def trade(context):
    if g.auto_day:
        target_list = rank_friend9_auto(context)[:g.target_num]
    else:
        target_list = rank_friend9_simple(context)[:g.target_num]
    hold_list = list(context.portfolio.positions.keys())
    for etf in hold_list:
        if etf not in target_list:
            order_target_value(etf, 0)
            log.info('[friend9] SELL %s %s' % (etf, get_security_info(etf).display_name))
    hold_list = list(context.portfolio.positions.keys())
    if len(hold_list) < g.target_num:
        value = context.portfolio.available_cash / max(1, g.target_num - len(hold_list))
        for etf in target_list:
            if context.portfolio.positions[etf].total_amount == 0:
                order_target_value(etf, value)
                log.info('[friend9] BUY %s %s value=%.2f' % (etf, get_security_info(etf).display_name, value))
'''


def friend9_script() -> str:
    pool = [
        "513100.XSHG",  # 纳指ETF
        "513520.XSHG",  # 日经ETF
        "513030.XSHG",  # 德国ETF
        "518880.XSHG",  # 黄金ETF
        "159980.XSHE",  # 有色ETF
        "501018.XSHG",  # 南方原油
        "511090.XSHG",  # 30年国债ETF
        "512890.XSHG",  # 红利低波
        "159915.XSHE",  # 创业板100
    ]
    header = "\n".join([
        "# Auto-generated from local ETF Loop research repo.",
        "# Strategy: friend9",
        "# JoinQuant account name suggestion: friend9_paper",
        "",
        f"FRIEND_POOL_9 = {pformat(pool, width=120, sort_dicts=False)}",
        "",
    ])
    return header + FRIEND_COMMON.strip() + "\n"


def write_readme() -> None:
    text = """# JoinQuant ETF Loop scripts

本目录由 `tools/export_joinquant_strategies.py` 生成，用于把本地 ETF Loop 候选策略复制到聚宽回测/模拟盘。

聚宽 API 核对来源：

- `https://www.joinquant.com/help/api/help#name:api`
- 实际内容接口：`https://www.joinquant.com/help/api/getContent?name=api`

本适配使用聚宽文档中的 `initialize`、`run_daily`、`attribute_history`、`get_price`、`get_extras`、`get_current_data`、`order_target_value`、`set_option('avoid_future_data', True)`、`set_slippage`、`PriceRelatedSlippage/FixedSlippage`、`set_order_cost/OrderCost`。

## 脚本

- `jq_F2_CAP_MA60.py`: F2_v3 核心池 + G2 PIT 月度动态池 + capped 动态补漏 + MA60 过热惩罚，Top5。
- `jq_WideA.py`: 在 `F2_CAP_MA60` 基础上加入 HS300 15 日收益的动态持仓数，参数为 `0.06,0.03,0,-0.02,-0.05,-0.08 -> 5,5,4,3,2,1,0`，总仓位恒为 100%。
- `jq_Exph_v3_exp_looser.py`: 在 `F2_CAP_MA60` 基础上加入 v3 的“总仓位”和“持仓数”分离规则，参数为 `0.05,0.02,0,-0.03,-0.06 -> N 5,5,4,4,3,0 -> exposure 1,1,0.85,0.65,0.45,0`。
- `jq_friend9.py`: friend 原始 9 ETF，Top1，ATR 动态 lookback，溢价惩罚，近期大跌过滤，09:50 运行。
- `jq_F2_CAP_MA60_current_month.py` / `jq_WideA_current_month.py` / `jq_Exph_v3_exp_looser_current_month.py`: 聚宽编辑器精简版，只写死当前月动态池，不包含 2018-2026 历史 PIT 大字典。
- `jq_WideA_fixed10.py`: 固定 10 ETF 池版本，只保留 WideA 打分和动态持仓，不启用动态 PIT 补漏。

## 重要差异

- F2/WideA/Exph 在聚宽版中于 `09:35` 运行，日线信号使用 `attribute_history` 在当前分钟可见的历史日线数据，不显式读取当天收盘价。
- F2/WideA/Exph 的 G2 PIT 月度动态池已经嵌入脚本；2026-06 会默认合并手工推荐 10 ETF 池。若要严格复现历史报告，把脚本里的 `g.use_manual_current_month_pool` 改成 `False`。
- 本地引擎使用复权后的 Tushare 日线口径；聚宽 `use_real_price=True` 下可能与本地复权口径略有差异，回测结果不应期望逐日完全一致。
- 当前聚宽脚本默认 `g.rebalance_existing=False`，即持有标的仍在目标池中就不强制调仓，贴近“在 top5 里继续持有”的模拟盘逻辑。
- F2/WideA/Exph 成本按本地候选口径设置：佣金 `1.5bp/边`，滑点 `2bp/边`。聚宽 `PriceRelatedSlippage(x)` 的 `x` 是买卖价差，脚本设置为 `0.0004`，买入/卖出各承担 `0.0002`。
- friend9 保留原始聚宽代码口径：`FixedSlippage(0.001)` + `open_commission/close_commission=0.0002`。
- 本地分钟执行层里的窗口参与率、拆单失败、连续冲击滑点、涨跌停阻断等是压力测试逻辑，不硬编码到聚宽模拟盘脚本。聚宽平台本身会按其撮合/滑点/交易成本模型执行；如果还想验证拆单，可以复制脚本后把 `run_daily(trade, '09:35')` 改成多个时点并自行拆分目标金额。
- `*_current_month.py` 只适合从当前月开始做聚宽平台回测/模拟盘准入。不要用它解释 2013-2026 研究回测，因为历史 PIT 动态池已被替换成当前月写死池。

## 使用

在 JoinQuant 新建策略/模拟盘账户，建议账户名：

- `F2_CAP_MA60_paper`
- `WideA_paper`
- `Exph_v3_exp_looser_paper`
- `friend9_paper`
- `WideA_fixed10_paper`

分别复制对应 `.py` 脚本到聚宽，先跑平台回测，再开模拟盘。

如果聚宽编辑器无法接受完整 PIT 版的大脚本，优先复制 `*_current_month.py`。
"""
    (OUT / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    f2 = load_f2_pool()
    pit = load_pit_pools()
    (OUT / "jq_F2_CAP_MA60.py").write_text(
        daily_strategy("F2_CAP_MA60", f2, pit),
        encoding="utf-8",
    )
    (OUT / "jq_WideA.py").write_text(
        daily_strategy(
            "WideA",
            f2,
            pit,
            adaptive_tiers_ret=[0.06, 0.03, 0.00, -0.02, -0.05, -0.08],
            adaptive_tiers_n=[5, 5, 4, 3, 2, 1, 0],
            adaptive_tiers_exposure=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0],
        ),
        encoding="utf-8",
    )
    (OUT / "jq_Exph_v3_exp_looser.py").write_text(
        daily_strategy(
            "Exph_v3_exp_looser",
            f2,
            pit,
            adaptive_tiers_ret=[0.05, 0.02, 0.00, -0.03, -0.06],
            adaptive_tiers_n=[5, 5, 4, 4, 3, 0],
            adaptive_tiers_exposure=[1.0, 1.0, 0.85, 0.65, 0.45, 0.0],
        ),
        encoding="utf-8",
    )
    (OUT / "jq_friend9.py").write_text(friend9_script(), encoding="utf-8")
    (OUT / "jq_F2_CAP_MA60_current_month.py").write_text(
        current_month_daily_strategy("F2_CAP_MA60", f2, MANUAL_202606),
        encoding="utf-8",
    )
    (OUT / "jq_WideA_current_month.py").write_text(
        current_month_daily_strategy(
            "WideA",
            f2,
            MANUAL_202606,
            adaptive_tiers_ret=[0.06, 0.03, 0.00, -0.02, -0.05, -0.08],
            adaptive_tiers_n=[5, 5, 4, 3, 2, 1, 0],
            adaptive_tiers_exposure=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0],
        ),
        encoding="utf-8",
    )
    (OUT / "jq_Exph_v3_exp_looser_current_month.py").write_text(
        current_month_daily_strategy(
            "Exph_v3_exp_looser",
            f2,
            MANUAL_202606,
            adaptive_tiers_ret=[0.05, 0.02, 0.00, -0.03, -0.06],
            adaptive_tiers_n=[5, 5, 4, 4, 3, 0],
            adaptive_tiers_exposure=[1.0, 1.0, 0.85, 0.65, 0.45, 0.0],
        ),
        encoding="utf-8",
    )
    (OUT / "jq_WideA_fixed10.py").write_text(
        fixed_pool_widea_strategy("WideA_fixed10", FIXED10_POOL),
        encoding="utf-8",
    )
    write_readme()
    print(f"Wrote JoinQuant scripts to {OUT}")


if __name__ == "__main__":
    main()
