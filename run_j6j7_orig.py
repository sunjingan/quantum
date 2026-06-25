#!/usr/bin/env python3
"""J6/J7 experiments using original (working) backtest function."""
import sys; sys.path.insert(0, '.')
from strategies.etf_loop_strategy import run_etf_loop_backtest, ETFLoopParams, _summarize
from pathlib import Path
import pandas as pd
import pickle

# Load G2 PIT pool as union
with open('data/tushare_cache/sector_prosperity/etf_pool_G2_PIT_monthly.pkl','rb') as f:
    pit_pools = pickle.load(f)
all_ts = sorted(set(c for pool in pit_pools.values() for c in pool))
print(f"Union pool: {len(all_ts)} ETFs")

token_path = Path('config/tushare_token.txt')
cache_dir = Path('data/tushare_cache')
out_dir = Path('outputs/etf_loop')
start = '2018-06-01'
end = '2026-06-25'

# J6: Fixed slippage variants
print()
print("=== J6 ===")
for tag, slip in [("J6_s001", 0.0001), ("J6_s005", 0.0005), ("J6_s010", 0.0010)]:
    params = ETFLoopParams(etf_pool_ts=all_ts, holdings_num=5, start=start, end=end, slippage=slip)
    equity, targets = run_etf_loop_backtest(cache_dir, token_path, params)
    stats = _summarize(equity)
    suffix = tag + "_h5_" + start.replace("-","") + "_" + end.replace("-","")
    equity.to_csv(out_dir / f"etf_loop_equity_{suffix}.csv")
    targets.to_csv(out_dir / f"etf_loop_targets_{suffix}.csv", index=False)
    pd.DataFrame([stats]).to_csv(out_dir / f"etf_loop_summary_{suffix}.csv", index=False)
    print(f"  {tag}: ann={stats['annual_return']*100:.2f}%, Sharpe={stats['sharpe_ratio']:.2f}, DD={stats['max_drawdown']*100:.2f}%, trades={len(targets)}")

# J7: Capacity proxy
print()
print("=== J7 ===")
for tag, cash in [("J7_500K", 500_000), ("J7_2M", 2_000_000)]:
    params = ETFLoopParams(etf_pool_ts=all_ts, holdings_num=5, start=start, end=end, initial_cash=cash, slippage=0.0005)
    equity, targets = run_etf_loop_backtest(cache_dir, token_path, params)
    stats = _summarize(equity)
    suffix = tag + "_h5_" + start.replace("-","") + "_" + end.replace("-","")
    equity.to_csv(out_dir / f"etf_loop_equity_{suffix}.csv")
    targets.to_csv(out_dir / f"etf_loop_targets_{suffix}.csv", index=False)
    pd.DataFrame([stats]).to_csv(out_dir / f"etf_loop_summary_{suffix}.csv", index=False)
    print(f"  {tag}: ann={stats['annual_return']*100:.2f}%, Sharpe={stats['sharpe_ratio']:.2f}, DD={stats['max_drawdown']*100:.2f}%, trades={len(targets)}")
print("Done!")
