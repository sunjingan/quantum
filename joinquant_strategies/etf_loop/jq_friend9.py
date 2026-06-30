# Auto-generated from local ETF Loop research repo.
# Strategy: friend9
# JoinQuant account name suggestion: friend9_paper

FRIEND_POOL_9 = ['513100.XSHG',
 '513520.XSHG',
 '513030.XSHG',
 '518880.XSHG',
 '159980.XSHE',
 '501018.XSHG',
 '511090.XSHG',
 '512890.XSHG',
 '159915.XSHE']
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
