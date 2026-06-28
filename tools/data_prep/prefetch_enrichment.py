#!/usr/bin/env python3
"""
富集数据预拉取脚本 — 一次性下载全部 8 个富集接口到磁盘缓存。

用法:
  source activate.sh
  python tools/data_prep/prefetch_enrichment.py --start 2018-01-01 --end 2026-06-22 --market hs300

拉取内容:
  - stk_holdertrade (内幕交易，逐只股票)
  - fina_audit       (审计意见)
  - pledge_stat      (质押比例)
  - dc_hot           (东财人气榜，仅近期)
  - limit_list_d     (涨跌停列表，仅近期)
  - moneyflow        (主力资金流向，仅近期)
  - margin_detail    (融资融券，仅近期)
  - ths_daily        (概念指数趋势)

所有数据落盘到 data/tushare_cache/enrichment/ 下，回测脚本自动复用。
"""
from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
import time
from pathlib import Path

multiprocessing.set_start_method("fork")

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from strategies._enrichment import EnrichmentCache
from strategies._utils import load_hs300_weights, read_instrument_codes
from strategies._fundamental import qlib_to_tushare


def main():
    parser = argparse.ArgumentParser(description="富集数据预拉取")
    parser.add_argument("--start", default="2000-01-04")
    parser.add_argument("--end", default="2026-06-22")
    parser.add_argument("--market", default="all_a")
    args = parser.parse_args()

    provider_uri = Path(os.environ.get("QLIB_PROVIDER_URI", BASE_DIR / "data" / "a_share_qlib"))
    token_path = BASE_DIR / "config" / "tushare_token.txt"
    cache_dir = BASE_DIR / "data" / "tushare_cache"

    print(f"富集数据预拉取")
    print(f"  区间: {args.start} — {args.end}")
    print(f"  市场: {args.market}")
    print(f"  数据源: {provider_uri}")
    print()

    # 获取股票池
    market = args.market.lower()
    if market in {"hs300", "csi300_history", "000300", "all_a"}:
        print("加载 HS300 历史成分股...")
        weights = load_hs300_weights(cache_dir, token_path, args.start, args.end)
        universe = sorted(weights["code"].str.lower().unique().tolist())
        print(f"  {len(universe)} 只历史成分股")
    else:
        universe = read_instrument_codes(provider_uri, market)
        print(f"  {len(universe)} 只股票")

    ts_codes = [qlib_to_tushare(c) for c in universe]
    print(f"  Tushare 代码: {len(ts_codes)} 只")
    print()

    # 初始化缓存
    ec = EnrichmentCache(token_path, cache_dir)
    print(f"缓存目录: {ec.cache_dir}")
    print()

    # 分步拉取
    t0 = time.time()

    print("=" * 60)
    print("Step 1/4: 内幕交易 (stk_holdertrade) — 逐只股票, 耗时较长")
    print("=" * 60)
    ec._fetch_insider(ts_codes, pd.Timestamp(args.start), pd.Timestamp(args.end))
    df = ec._insider_cache.get("_all", pd.DataFrame())
    print(f"  完成: {len(df)} 条记录, 耗时 {time.time() - t0:.1f}s\n")

    print("=" * 60)
    print("Step 2/4: 审计意见 + 质押比例 (fina_audit + pledge_stat)")
    print("=" * 60)
    ec._fetch_audit(ts_codes)
    df_a = ec._audit_cache.get("_all", pd.DataFrame())
    print(f"  fina_audit: {len(df_a)} 条")

    ec._fetch_pledge()
    df_p = ec._pledge_cache
    n_p = len(df_p) if df_p is not None and not df_p.empty else 0
    print(f"  pledge_stat: {n_p} 条")
    print(f"  耗时 {time.time() - t0:.1f}s\n")

    print("=" * 60)
    print("Step 3/4: 每日数据 (dc_hot, limit_list_d, moneyflow, margin_detail)")
    print("  = 仅拉取近1年数据（历史数据不可用）")
    print("=" * 60)
    ec._fetch_dc_hot(pd.Timestamp(args.start), pd.Timestamp(args.end))
    df_h = ec._dc_hot_cache.get("_all", pd.DataFrame())
    print(f"  dc_hot: {len(df_h)} 条")

    ec._fetch_limit_list(pd.Timestamp(args.start), pd.Timestamp(args.end))
    df_l = ec._limit_list_cache.get("_all", pd.DataFrame())
    print(f"  limit_list_d: {len(df_l)} 条")

    ec._fetch_moneyflow(ts_codes, pd.Timestamp(args.start), pd.Timestamp(args.end))
    df_m = ec._moneyflow_cache.get("_all", pd.DataFrame())
    print(f"  moneyflow: {len(df_m)} 条")

    ec._fetch_margin(ts_codes, pd.Timestamp(args.start), pd.Timestamp(args.end))
    df_mg = ec._margin_cache.get("_all", pd.DataFrame())
    print(f"  margin_detail: {len(df_mg)} 条")
    print(f"  耗时 {time.time() - t0:.1f}s\n")

    print("=" * 60)
    print("Step 4/4: 概念指数 (ths_daily)")
    print("=" * 60)
    ec._fetch_ths_concepts(pd.Timestamp(args.start), pd.Timestamp(args.end))
    df_t = ec._ths_daily_cache.get("_all", pd.DataFrame())
    print(f"  ths_daily: {len(df_t)} 条")
    print(f"  耗时 {time.time() - t0:.1f}s\n")

    # 统计
    total = time.time() - t0
    all_rows = len(df) + len(df_a) + n_p + len(df_h) + len(df_l) + len(df_m) + len(df_mg) + len(df_t)
    print("=" * 60)
    print(f"富集数据全部拉取完成!")
    print(f"  总耗时: {total:.1f}s")
    print(f"  总记录: {all_rows} 条")
    print(f"  缓存目录: {ec.cache_dir}")
    print()
    print(f"现在可以跑回测:")
    print(f"  QLIB_PROVIDER_URI=data/a_share_qlib python runs/qlib/backtest_v2.py \\")
    print(f"    --start {args.start} --end {args.end} --target-num 10")


if __name__ == "__main__":
    main()
