#!/usr/bin/env python3
"""Mean reversion penalty test — avoid buying cyclical ETFs at momentum peaks."""
import os, sys
sys.path.insert(0, '.')
os.environ['QLIB_PROVIDER_URI'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'a_share_qlib')
import pandas as pd, numpy as np
from pathlib import Path
from strategies.etf_loop_strategy import (
    ETFDailyStore, SectorProsperityCache, get_ranked_etfs,
    _summarize, calculate_atr, _lot_floor, FULL_ETF_POOL_JQ, _jq_to_ts,
)
from strategies._utils import QlibDailyReader

df = pd.read_csv('data/tushare_cache/sector_prosperity/etf_pool_F2_v3.csv', dtype={'ts_code': str})
pool_big = set(df['ts_code'].tolist()) | set(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
supp = ['512690.SH','515790.SH','515030.SH','159865.SZ','159867.SZ',
    '515220.SH','515210.SH','159928.SZ','512980.SH','159766.SZ']
pool_all = sorted(pool_big | set(supp))

class P: pass
P = P()
P.holdings_num = 5; P.lookback_days = 25; P.stop_loss = 0.95
P.use_rsi_filter = True; P.rsi_period = 6; P.rsi_lookback_days = 1; P.rsi_threshold = 98
P.enable_volume_check = True; P.volume_lookback = 5; P.volume_threshold = 2.0; P.volume_return_limit = 1.0
P.use_short_momentum_filter = True; P.short_lookback_days = 10; P.short_momentum_threshold = 0.0
P.loss = 0.97; P.min_score_threshold = 0.0; P.max_score_threshold = 500.0
P.use_atr_stop_loss = True; P.atr_period = 14; P.atr_multiplier = 2.0

START, END = '2013-07-01', '2026-06-25'

for label, mr_enabled, mr_ma, mr_threshold, mr_penalty in [
    ("BASELINE", False, 0, 0, 0),
    ("MR_MA200_1.3x_0.5", True, 200, 1.3, 0.5),
    ("MR_MA200_1.5x_0.5", True, 200, 1.5, 0.5),
    ("MR_MA150_1.3x_0.3", True, 150, 1.3, 0.3),
]:
    cache = SectorProsperityCache(Path('config/tushare_token.txt'), Path('data/tushare_cache'))
    store = ETFDailyStore(cache, pool_all, START, END)
    reader = QlibDailyReader(Path(os.environ['QLIB_PROVIDER_URI']))
    bc = reader.read_field("sh000300", "close")
    bc = bc.loc[pd.Timestamp(START):pd.Timestamp(END)]
    
    cal = store.calendar
    CASH = 500_000
    S, EP, PH = {}, {}, {}
    recs, trows = [], []
    
    for i, dd in enumerate(cal[:-1]):
        if i < max(25, mr_ma) + 5:
            continue
        nd = cal[i + 1]
        
        temp_codes = store.ts_codes
        store.ts_codes = list(set(pool_all) & set(store.ts_codes))
        ranked = get_ranked_etfs(store, dd, P)
        store.ts_codes = temp_codes
        
        # Mean reversion penalty
        if mr_enabled and len(ranked) > 1:
            for r in ranked:
                prices = store.price_series(r['ts_code'], dd, mr_ma + 5)
                if len(prices) >= mr_ma:
                    ma = np.mean(prices[-mr_ma:])
                    ratio = prices[-1] / ma if ma > 0 else 1.0
                    if ratio >= mr_threshold:
                        r['score'] *= mr_penalty
            ranked.sort(key=lambda x: x['score'], reverse=True)
        
        tc = set(r['ts_code'] for r in ranked[:5])
        nop = {}
        for c in (tc | set(S.keys())):
            if c in store.open.columns:
                col = store.open[c].loc[:nd].dropna()
                if not col.empty:
                    nop[c] = float(col.iloc[-1])
        
        for c in list(S.keys()):
            if S.get(c, 0) <= 0:
                continue
            sp = store.latest_price(c, dd)
            epx = nop.get(c, np.nan)
            if np.isnan(epx) or epx <= 0:
                epx = sp
            if np.isnan(epx) or epx <= 0:
                continue
            st = c in EP and sp <= EP[c] * 0.95
            at = False
            ohlc = store.ohlc_series(c, dd, P.atr_period + 20)
            if ohlc is not None:
                av = calculate_atr(ohlc["high"], ohlc["low"], ohlc["close"], P.atr_period)
                if av > 0 and sp <= EP.get(c, sp) - P.atr_multiplier * av:
                    at = True
            if (c not in tc) or st or at:
                CASH += S[c] * epx * (1 - 0.0001) * (1 - 0.0001)
                trows.append({'date': dd, 'trade_date': nd, 'ts_code': c, 'action': 'SELL', 'price': epx, 'shares': S[c]})
                S[c] = 0
                EP.pop(c, None)
                PH.pop(c, None)
        
        aset = tc | set(c for c in S if S.get(c, 0) > 0)
        if aset:
            na = max(1, len(aset))
            TVV = CASH
            for c in S:
                if S.get(c, 0) > 0:
                    px = store.latest_price(c, dd)
                    TVV += S[c] * (px if not np.isnan(px) and px > 0 else 0)
            PS = TVV / na
            for c in sorted(tc):
                px = nop.get(c, np.nan)
                if np.isnan(px) or px <= 0:
                    continue
                cv = S.get(c, 0) * px
                diff = PS - cv
                if diff <= 0:
                    continue
                buy_cash = min(CASH, diff)
                bs = _lot_floor(buy_cash / (px * (1 + 0.0001 + 0.0001)))
                if bs <= 0:
                    continue
                tv = bs * px
                if tv < 5000:
                    continue
                CASH -= tv * (1 + 0.0001 + 0.0001)
                old = S.get(c, 0)
                S[c] = old + bs
                if old == 0:
                    EP[c] = px
                    PH[c] = px
                else:
                    EP[c] = (old * EP[c] + bs * px) / (old + bs)
                trows.append({'date': dd, 'trade_date': nd, 'ts_code': c, 'action': 'BUY', 'price': px, 'shares': bs,
                              'score': next((r['score'] for r in ranked if r['ts_code'] == c), np.nan)})
        
        for c in S:
            if S.get(c, 0) <= 0:
                continue
            pc = store.latest_price(c, nd)
            if not np.isnan(pc) and pc > 0:
                PH[c] = max(PH.get(c, pc), pc)
        PV = CASH
        for c in S:
            if S.get(c, 0) > 0:
                px = store.latest_price(c, nd)
                PV += S[c] * (px if not np.isnan(px) and px > 0 else EP.get(c, 0))
        recs.append({'date': nd, 'portfolio_value': PV, 'cash': CASH, 'pos': sum(1 for s in S.values() if s > 0)})
    
    equity = pd.DataFrame(recs).drop_duplicates('date', keep='last').set_index('date')
    vals = equity['portfolio_value']
    dr = vals.pct_change().dropna()
    ann = dr.mean() * 252 * 100
    ddv = (vals / vals.cummax() - 1).min() * 100
    sh = dr.mean() / dr.std() * np.sqrt(252)
    print(f"{label:25s}: ann={ann:6.2f}% DD={ddv:6.2f}% Sharpe={sh:.2f} trades={len(trows)}")

print(f"\nReference: F2_v3 ∪ ORIG38 (64 ETFs) = 31.10% DD=-19.74% Sharpe=1.28")
