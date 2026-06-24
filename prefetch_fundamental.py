#!/usr/bin/env python3
"""全量 A 股基础财务数据预拉取 — 后台运行。"""
import multiprocessing; multiprocessing.set_start_method("fork")
import os, sys, time
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

from strategies._fundamental import FundamentalCache, qlib_to_tushare
from strategies._utils import read_instrument_codes

PROVIDER_URI = BASE_DIR / "data" / "a_share_qlib"
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"

start, end = "2000-01-04", "2026-06-22"
universe = read_instrument_codes(PROVIDER_URI, "all_a")
ts_codes = [qlib_to_tushare(c) for c in universe]
print(f"全量 A 股: {len(ts_codes)} 只, {start} — {end}")
print(f"缓存目录: {CACHE_DIR / 'trend_serenity'}")

data = FundamentalCache(TOKEN_PATH, CACHE_DIR / "trend_serenity")
t0 = time.time()
data.prefetch(ts_codes, start, end)
elapsed = time.time() - t0
print(f"\n基础财务数据全部缓存完成! 耗时 {elapsed:.0f}s ({elapsed/60:.1f}min)")
print(f"后续回测将直接读磁盘缓存，秒级启动")
