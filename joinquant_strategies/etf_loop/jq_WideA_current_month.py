# Auto-generated from local ETF Loop research repo.
# Strategy: WideA_current_month
# JoinQuant account name suggestion: WideA_current_month_paper
# This compact script hard-codes only the current dynamic pool. Do not use it
# to interpret long historical PIT backtests.


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



CORE_POOL = ['159201.XSHE',
 '159399.XSHE',
 '159516.XSHE',
 '159570.XSHE',
 '159682.XSHE',
 '159792.XSHE',
 '159870.XSHE',
 '159887.XSHE',
 '159915.XSHE',
 '159919.XSHE',
 '159949.XSHE',
 '159981.XSHE',
 '159995.XSHE',
 '160723.XSHE',
 '161226.XSHE',
 '501018.XSHG',
 '510050.XSHG',
 '510500.XSHG',
 '510880.XSHG',
 '511360.XSHG',
 '511380.XSHG',
 '511880.XSHG',
 '511990.XSHG',
 '512070.XSHG',
 '512100.XSHG',
 '512400.XSHG',
 '512480.XSHG',
 '512880.XSHG',
 '512890.XSHG',
 '513050.XSHG',
 '513090.XSHG',
 '513100.XSHG',
 '513120.XSHG',
 '513180.XSHG',
 '513310.XSHG',
 '513330.XSHG',
 '513400.XSHG',
 '513500.XSHG',
 '513520.XSHG',
 '515180.XSHG',
 '515880.XSHG',
 '518850.XSHG',
 '562500.XSHG',
 '588000.XSHG']
CURRENT_DYNAMIC_POOL = ['588000.XSHG',
 '159995.XSHE',
 '515070.XSHG',
 '562500.XSHG',
 '512880.XSHG',
 '512890.XSHG',
 '159928.XSHE',
 '159941.XSHE',
 '518880.XSHG',
 '159930.XSHE']


def initialize(context):
    setup_platform()
    g.strategy_name = 'WideA_current_month'
    g.account_name = 'WideA_current_month_paper'
    g.core_pool = CORE_POOL
    # Keep the current pool active from 2026-06 onward; update this monthly.
    g.dynamic_pit_pools = {'2026-06': CURRENT_DYNAMIC_POOL}
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
