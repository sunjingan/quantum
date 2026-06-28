#!/usr/bin/env python3
"""Download broad market index data via Tushare and save as CSV for benchmark use."""
from __future__ import annotations
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import pandas as pd
from strategies.etf_loop_strategy import SectorProsperityCache

TOKEN = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"

# Read token
with open(TOKEN) as f:
    token = f.read().strip()

import tushare as ts
ts.set_token(token)
pro = ts.pro_api()

BENCHMARKS = {
    "sh000300": "000300.SH",   # 沪深300
    "sh000905": "000905.SH",   # 中证500
    "sh000852": "000852.SH",   # 中证1000
    "sz399006": "399006.SZ",   # 创业板指
}

OUT_DIR = CACHE_DIR / "benchmarks"
OUT_DIR.mkdir(parents=True, exist_ok=True)

for qlib_code, ts_code in BENCHMARKS.items():
    out_path = OUT_DIR / f"{qlib_code}.csv"
    if out_path.exists():
        print(f"{qlib_code}: skip existing")
        continue
    
    print(f"{qlib_code}: downloading {ts_code}...")
    try:
        df = pro.index_daily(ts_code=ts_code, start_date="20050101", end_date="20260627",
                             fields="trade_date,open,high,low,close,vol,amount")
        if df is not None and len(df) > 0:
            df = df.sort_values("trade_date")
            df.to_csv(out_path, index=False)
            print(f"  → {len(df)} rows saved to {out_path}")
        else:
            print(f"  → No data returned")
    except Exception as e:
        print(f"  → Error: {e}")

print("\nDone. Check", OUT_DIR)
