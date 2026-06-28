#!/usr/bin/env python3
"""Cache the data needed by the theme ETF experiment suite.

This script is intentionally broad: it caches ETF metadata / daily / share,
all-A fundamentals, daily_basic snapshots, moneyflow, top_inst, and index
weights for ETF underlyings so later experiments can run from local disk.

Examples:
  source activate.sh
  QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
    python tools/data_prep/prefetch_theme_etf_data.py --start 2018-01-02 --end 2026-06-22 --market all_a
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


def _iter_dates(start: str, end: str) -> list[pd.Timestamp]:
    from strategies._utils import QlibDailyReader

    reader = QlibDailyReader(Path(os.environ.get("QLIB_PROVIDER_URI", BASE_DIR / "data" / "a_share_qlib")))
    cal = reader.calendar
    return [d for d in cal if pd.Timestamp(start) <= d <= pd.Timestamp(end)]


def _prefetch_daily_basic(data, dates: list[pd.Timestamp]) -> None:
    for i, dt in enumerate(dates, start=1):
        data.daily_basic(dt)
        if i % 50 == 0:
            print(f"  daily_basic: {i}/{len(dates)}")


def _prefetch_top_inst(cache, dates: list[pd.Timestamp]) -> None:
    for i, dt in enumerate(dates, start=1):
        ymd = f"{dt:%Y%m%d}"
        cache._cached_fetch(f"top_inst_{ymd}", lambda d=ymd: cache._safe_fetch("top_inst", trade_date=d))
        if i % 50 == 0:
            print(f"  top_inst: {i}/{len(dates)}")


def _prefetch_index_weights(cache, start: str, end: str) -> None:
    etf_basic = cache.etf_basic()
    if etf_basic.empty or "index_code" not in etf_basic.columns:
        print("  index_weight: skipped (no ETF basic index_code)")
        return
    index_codes = (
        etf_basic["index_code"]
        .dropna()
        .astype(str)
        .replace({"nan": ""})
        .loc[lambda s: s.str.len() > 0]
        .drop_duplicates()
        .tolist()
    )
    print(f"  index_weight targets: {len(index_codes)}")
    for i, index_code in enumerate(index_codes, start=1):
        cache.index_weight(index_code, start, end)
        if i % 20 == 0:
            print(f"  index_weight: {i}/{len(index_codes)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache theme ETF experiment data")
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="2026-06-22")
    parser.add_argument("--market", default="all_a")
    parser.add_argument("--skip-fundamentals", action="store_true")
    parser.add_argument("--skip-daily-basic", action="store_true")
    parser.add_argument("--skip-moneyflow", action="store_true")
    parser.add_argument("--skip-top-inst", action="store_true")
    parser.add_argument("--skip-etf", action="store_true")
    parser.add_argument("--skip-index-weight", action="store_true")
    args = parser.parse_args()

    provider_uri = Path(os.environ.get("QLIB_PROVIDER_URI", BASE_DIR / "data" / "a_share_qlib"))
    token_path = BASE_DIR / "config" / "tushare_token.txt"
    cache_dir = BASE_DIR / "data" / "tushare_cache"
    theme_cache_dir = cache_dir / "theme_etf_momentum"

    print("Theme ETF data prefetch")
    print(f"  provider: {provider_uri}")
    print(f"  market:   {args.market}")
    print(f"  range:    {args.start} -> {args.end}")
    print(f"  cache:    {cache_dir}")
    print("  phase:    importing strategy modules")

    from strategies._fundamental import FundamentalCache, qlib_to_tushare
    from strategies._utils import read_instrument_codes
    from strategies.sector_prosperity import SectorProsperityCache

    print("  phase:    imports ready")

    dates = _iter_dates(args.start, args.end)
    print(f"  trading dates: {len(dates)}")

    t0 = time.time()
    universe = read_instrument_codes(provider_uri, args.market)
    ts_codes = [qlib_to_tushare(c) for c in universe]
    print(f"  universe: {len(universe)} stocks")

    if not args.skip_etf:
        print("\n[1/5] ETF metadata / daily / share")
        sec = SectorProsperityCache(token_path, cache_dir)
        sec.prefetch_etf_data(args.start, args.end)

    if not args.skip_index_weight:
        print("\n[2/5] ETF constituent weights")
        sec = SectorProsperityCache(token_path, cache_dir)
        sec.prefetch_etf_data(args.start, args.end)
        _prefetch_index_weights(sec, args.start, args.end)

    if not args.skip_fundamentals:
        print("\n[3/5] fundamentals")
        fund = FundamentalCache(token_path, theme_cache_dir)
        fund.stock_basic()
        fund.prefetch(ts_codes, args.start, args.end)

    if not args.skip_daily_basic:
        print("\n[4/5] daily_basic")
        fund = FundamentalCache(token_path, theme_cache_dir)
        _prefetch_daily_basic(fund, dates)

    if not args.skip_moneyflow or not args.skip_top_inst:
        print("\n[5/5] enrichment")
        from strategies._enrichment import EnrichmentCache

        enrich = EnrichmentCache(token_path, cache_dir)
        if not args.skip_moneyflow:
            enrich._fetch_moneyflow(ts_codes, pd.Timestamp(args.start), pd.Timestamp(args.end))
        if not args.skip_top_inst:
            _prefetch_top_inst(SectorProsperityCache(token_path, cache_dir), dates)

    elapsed = time.time() - t0
    print("\nPrefetch complete")
    print(f"  elapsed: {elapsed:.1f}s")
    print(f"  theme cache dir: {theme_cache_dir}")


if __name__ == "__main__":
    main()
