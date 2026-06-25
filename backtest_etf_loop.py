#!/usr/bin/env python3
"""ETF Loop Momentum Rotation — backtest runner.

Ported from the JoinQuant 七星高照ETF轮动策略.
Uses the project's fund_daily caches (SectorProsperityCache) for ETF OHLCV data.

Usage:
  # Quick backtest with default pool and parameters
  python backtest_etf_loop.py --start 2021-01-01 --end 2026-06-22

  # Fetch ETF data from Tushare (fund_daily for the pool)
  python backtest_etf_loop.py --fetch --start 2018-01-01 --end 2026-06-22

  # Custom parameters
  python backtest_etf_loop.py --holdings-num 3 --lookback 30 --no-rsi --no-volume
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROVIDER_URI = Path(os.environ.get("QLIB_PROVIDER_URI", BASE_DIR / "data" / "a_share_qlib"))
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
OUT_DIR = BASE_DIR / "outputs"

sys.path.insert(0, str(BASE_DIR))

from strategies.etf_loop_strategy import (
    _build_all_etf_pool,
    ETFLoopParams,
    FULL_ETF_POOL_JQ,
    _jq_to_ts,
    run_etf_loop_backtest,
    output_paths,
    _summarize,
)


def fetch_etf_daily(token_path: Path, cache_dir: Path, ts_codes: list[str], start: str, end: str):
    """Fetch fund_daily data from Tushare and save to the sector_prosperity cache."""
    import tushare as ts
    from datetime import timedelta

    token = token_path.read_text().strip()
    pro = ts.pro_api(token=token)
    out_dir = cache_dir / "sector_prosperity"
    out_dir.mkdir(parents=True, exist_ok=True)

    cursor = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    total = 0
    while cursor <= end_ts:
        ymd = cursor.strftime("%Y%m%d")
        path = out_dir / f"fund_daily_{ymd}.csv"
        if path.exists():
            cursor += timedelta(days=1)
            continue

        try:
            df = pro.fund_daily(trade_date=ymd)
        except Exception as e:
            print(f"  fetch {ymd}: {e}")
            cursor += timedelta(days=1)
            continue

        if df is not None and not df.empty:
            # Filter to our ETF pool
            df_etf = df[df["ts_code"].isin(ts_codes)].copy()
            if not df_etf.empty:
                df_etf.to_csv(path, index=False)
                total += 1
                print(f"  saved {ymd}: {len(df_etf)} ETF records")

        cursor += timedelta(days=1)

    print(f"Fetched {total} new trading days of fund_daily data.")


def main():
    p = argparse.ArgumentParser(description="ETF Loop Momentum Rotation Backtest")
    p.add_argument("--start", default="2021-01-01")
    p.add_argument("--end", default="2026-06-22")
    p.add_argument("--initial-cash", type=float, default=500_000.0)
    p.add_argument("--holdings-num", type=int, default=2)
    p.add_argument("--lookback", type=int, default=25, help="Momentum lookback days")
    p.add_argument("--stop-loss", type=float, default=0.95)
    p.add_argument("--no-rsi", action="store_true", help="Disable RSI filter")
    p.add_argument("--no-volume", action="store_true", help="Disable volume filter")
    p.add_argument("--no-short-momentum", action="store_true", help="Disable short momentum filter")
    p.add_argument("--no-atr", action="store_true", help="Disable ATR stop loss")
    p.add_argument("--atr-trailing", action="store_true", help="Use trailing ATR stop")
    p.add_argument("--fetch", action="store_true", help="Fetch ETF daily data from Tushare")
    p.add_argument("--pool", choices=["full", "small", "all"], default="full")
    args = p.parse_args()

    # Build pool
    if args.pool == "small":
        small_pool_jq = [
            "518880.XSHG", "159985.XSHE", "501018.XSHG", "513100.XSHG", "159915.XSHE", "511220.XSHG",
        ]
        pool_ts = [_jq_to_ts(c) for c in small_pool_jq]
    elif args.pool == "all":
        print("Building all-ETF pool from Tushare + cache...")
        pool_ts = _build_all_etf_pool(TOKEN_PATH, CACHE_DIR)
        print(f"  Pool size: {len(pool_ts)} ETFs")
    else:
        pool_ts = [_jq_to_ts(c) for c in FULL_ETF_POOL_JQ]

    # Fetch if requested
    if args.fetch:
        print(f"Fetching fund_daily for {len(pool_ts)} ETFs: {args.start} — {args.end}")
        fetch_etf_daily(TOKEN_PATH, CACHE_DIR, pool_ts, args.start, args.end)

    params = ETFLoopParams(
        etf_pool_ts=pool_ts,
        initial_cash=args.initial_cash,
        holdings_num=args.holdings_num,
        lookback_days=args.lookback,
        stop_loss=args.stop_loss,
        use_rsi_filter=not args.no_rsi,
        enable_volume_check=not args.no_volume,
        use_short_momentum_filter=not args.no_short_momentum,
        use_atr_stop_loss=not args.no_atr,
        atr_trailing_stop=args.atr_trailing,
        start=args.start,
        end=args.end,
    )

    print(f"ETF Loop 回测: {args.start} — {args.end}")
    print(f"  ETF池: {len(pool_ts)} 只  持仓数: {args.holdings_num}  动量周期: {args.lookback}天")
    print(f"  RSI: {'✓' if params.use_rsi_filter else '✗'}  "
          f"成交量: {'✓' if params.enable_volume_check else '✗'}  "
          f"短期动量: {'✓' if params.use_short_momentum_filter else '✗'}  "
          f"ATR: {'✓' if params.use_atr_stop_loss else '✗'}")

    equity, targets = run_etf_loop_backtest(CACHE_DIR, TOKEN_PATH, params)

    tag = f"{args.pool}_h{args.holdings_num}"
    paths = output_paths(OUT_DIR, args.start, args.end, tag)
    equity.to_csv(paths["equity"])
    targets.to_csv(paths["targets"], index=False)

    # Plot
    fig, ax = plt.subplots(figsize=(14, 7))
    (equity["strategy_return"] * 100).plot(ax=ax, label="ETF Loop Strategy", linewidth=2)
    if "benchmark_return" in equity.columns and equity["benchmark_return"].notna().any():
        (equity["benchmark_return"] * 100).plot(ax=ax, label="CSI 300", linewidth=1.8, alpha=0.7)
    ax.set_title("ETF Loop Momentum Rotation")
    ax.set_ylabel("Cumulative Return (%)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(paths["plot"], dpi=160)
    plt.close(fig)

    # Stats
    stats = _summarize(equity)
    pd.DataFrame([stats]).to_csv(paths["summary"], index=False)

    print(f"\n{'='*60}")
    print("ETF Loop 回测结果")
    print(f"{'='*60}")
    print(f"区间: {args.start} — {args.end}")
    print(f"ETF池: {len(pool_ts)} 只 | 数据覆盖: {len(set(targets['ts_code']) if not targets.empty else [])} 只")
    for k, v in stats.items():
        if v is not None and not np.isnan(v):
            if "drawdown" in k:
                print(f"  {k}: {v*100:.2f}%")
            elif k in ("total_return",):
                print(f"  {k}: {v*100:.2f}%")
            elif k == "final_value":
                print(f"  {k}: {v:,.0f}")
            else:
                print(f"  {k}: {v*100:.2f}%")
    print(f"\n  净值: {paths['equity']}")
    print(f"  交易: {paths['targets']}")
    print(f"  统计: {paths['summary']}")
    print(f"  曲叶: {paths['plot']}")
    print(f"\n本回测不构成投资建议。")


if __name__ == "__main__":
    main()
