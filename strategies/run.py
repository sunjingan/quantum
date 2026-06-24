"""
Unified CLI entry point for qlib-integrated fundamental strategies.

Usage:
  source activate.sh

  # POE PB+ROE strategy
  python -m strategies.run poe_pb_roe --market hs300 --start 2018-01-02

  # Trend-Serenity strategy
  python -m strategies.run trend_serenity --market hs300 --start 2018-01-02 --end 2026-06-22

  # Theme ETF momentum strategy
  python -m strategies.run theme_etf_momentum --market all_a --start 2018-01-02 --end 2026-06-22 --experiment v3 --theme-source real_etf

  # Via qrun (uses YAML configs)
  qrun config/trend_serenity_qlib.yaml
  qrun config/poe_pb_roe_qlib.yaml

This module supports two execution modes:
  1. Direct Python: uses the manual backtest loop (existing scripts' logic)
  2. qrun YAML: uses qlib's SimulatorExecutor with custom Strategy classes
"""
from __future__ import annotations

import argparse
import datetime as dt
import multiprocessing
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

multiprocessing.set_start_method("fork")

PROVIDER_URI = Path(os.environ.get("QLIB_PROVIDER_URI", BASE_DIR / "data" / "my_qlib"))
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
BENCHMARK = "sh000300"


def run_manual_backtest(strategy_name: str, args: argparse.Namespace):
    """Run the manual backtest loop (compatible with existing scripts)."""
    from strategies._fundamental import FundamentalCache, qlib_to_tushare
    from strategies._utils import (
        Hs300HistoryUniverse,
        QlibDailyReader,
        load_hs300_weights,
        lot_floor,
        monthly_rebalance_dates,
        read_instrument_codes,
        summarize,
    )

    if strategy_name == "trend_serenity":
        from strategies.trend_serenity import (
            TrendSerenityParams,
            build_serenity_pool_v2,
            select_targets_v2,
        )
        from strategies.trend_serenity_v2 import compute_serenity_v2, select_serenity_v2_targets
        from strategies._enrichment import EnrichmentCache, compute_enrichment_for_codes
        ParamsClass = TrendSerenityParams
        USE_ENRICHMENT = True
    elif strategy_name == "poe_pb_roe":
        from strategies.poe_pb_roe import (
            POEPBRoeParams,
            build_base_dataframe,
            pick_targets,
        )
        from strategies._utils import market_state as market_state_fn
        ParamsClass = POEPBRoeParams
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    if strategy_name == "trend_serenity":
        params = ParamsClass(
            initial_cash=args.initial_cash,
            benchmark=BENCHMARK,
            market=args.market,
            factor_version=args.factor_version,
            use_buffer=not args.no_buffer,
        )
    else:
        params = ParamsClass(initial_cash=args.initial_cash, benchmark=BENCHMARK, market=args.market)

    # Resolve universe
    history_universe = None
    if args.market.lower() in {"hs300", "csi300_history", "000300"}:
        weights = load_hs300_weights(CACHE_DIR, TOKEN_PATH, args.start, args.end)
        history_universe = Hs300HistoryUniverse(weights)
        universe = sorted(weights["code"].str.lower().unique().tolist())
    else:
        universe = read_instrument_codes(PROVIDER_URI, args.market)

    # Lazy Tushare -> Qlib
    from lazy_tushare_loader import LazyTushareLoader
    if os.environ.get("QLIB_LAZY_TUSHARE", "1") != "0":
        LazyTushareLoader.for_project(BASE_DIR, PROVIDER_URI).ensure(
            instruments=universe,
            start_time=args.start,
            end_time=args.end,
            benchmark=BENCHMARK.upper(),
        )
    else:
        print("Lazy Tushare: skipped by QLIB_LAZY_TUSHARE=0")

    reader = QlibDailyReader(PROVIDER_URI)
    all_codes = sorted(set(universe + [BENCHMARK]))
    close = reader.close_frame(all_codes, args.start, args.end)
    stock_close = close[[c for c in universe if c in close.columns]]
    bench_close = close[BENCHMARK]

    data = FundamentalCache(TOKEN_PATH, CACHE_DIR / strategy_name)
    ts_codes = [qlib_to_tushare(c) for c in universe]
    data.prefetch(ts_codes, args.start, args.end)

    cash = params.initial_cash
    shares = pd.Series(0.0, index=stock_close.columns)
    records, target_rows = [], []
    rebal_dates = set(monthly_rebalance_dates(reader.calendar, args.start, args.end))

    for i, date in enumerate(stock_close.index[:-1]):
        next_date = stock_close.index[i + 1]
        prices = stock_close.loc[date]

        if date in rebal_dates and i > 0:
            data_date = stock_close.index[i - 1]
            active_universe = history_universe.codes_for_date(data_date) if history_universe else universe

            if strategy_name == "trend_serenity":
                if args.factor_version == "v2":
                    pool = compute_serenity_v2(
                        data,
                        None,
                        stock_close,
                        active_universe,
                        data_date,
                        industry_neutral=params.industry_neutral_v2,
                    )
                    hard_excl = pd.DataFrame()
                    current_holdings = set(shares[shares > 0].index)
                    targets = select_serenity_v2_targets(
                        pool,
                        current_holdings=current_holdings if params.use_buffer else set(),
                        target_num=params.target_num,
                        buy_top_n=params.buy_top_n,
                        hold_threshold_n=params.hold_threshold_n if params.use_buffer else 0,
                        max_per_industry=params.max_per_industry,
                    ) if pool is not None and not pool.empty else []
                    branch = f"SERENITY_V2(buffer={params.use_buffer})"
                else:
                    enrich = EnrichmentCache(TOKEN_PATH, CACHE_DIR)
                    enrich.prefetch([qlib_to_tushare(c) for c in active_universe], str(data_date.date()), str(data_date.date()))
                    pool, hard_excl = build_serenity_pool_v2(data, enrich, stock_close, active_universe, data_date, params)
                    targets = select_targets_v2(pool, params) if not pool.empty else []
                    n_a = (pool["tier"] == "Pass-A").sum() if not pool.empty else 0
                    n_b = (pool["tier"] == "Pass-B").sum() if not pool.empty else 0
                    n_c = (pool["tier"] == "Pass-C").sum() if not pool.empty else 0
                    branch = f"SERENITY_V1(A:{n_a}B:{n_b}C:{n_c} excl:{len(hard_excl)})"
            else:
                base_df = build_base_dataframe(data, active_universe, data_date, params)
                if not base_df.empty:
                    m_state, risk_state = market_state_fn(bench_close, data_date)
                    targets, pool, branch = pick_targets(base_df, m_state, risk_state, params)
                else:
                    targets, branch = [], "EMPTY"

            target_set = set(targets)

            # Sell
            for code in shares.index:
                if shares[code] > 0 and code not in target_set and pd.notnull(prices.get(code, np.nan)):
                    cash += shares[code] * prices[code] * (1 - params.close_cost)
                    shares[code] = 0

            # Buy (equal weight)
            if targets:
                total_value = cash + float((shares * prices.fillna(0)).sum())
                target_value = total_value / len(targets)
                for code in targets:
                    price = prices.get(code, np.nan)
                    if pd.isnull(price) or price <= 0:
                        continue
                    current_value = shares.get(code, 0.0) * price
                    diff_value = target_value - current_value
                    if diff_value < 0:
                        sell_shares = min(shares.get(code, 0.0), lot_floor(abs(diff_value) / price))
                        cash += sell_shares * price * (1 - params.close_cost)
                        shares[code] -= sell_shares
                    elif diff_value > 0:
                        buy_cash = min(cash, diff_value)
                        buy_shares = lot_floor(buy_cash / (price * (1 + params.open_cost)))
                        cash -= buy_shares * price * (1 + params.open_cost)
                        shares[code] += buy_shares

            for rank, code in enumerate(targets, start=1):
                target_rows.append({"date": date, "rank": rank, "code": code, "branch": branch})
            print(f"{date.date()} {strategy_name} rebalance [{branch}]: {len(targets)} targets")

        next_prices = stock_close.loc[next_date]
        value = cash + float((shares * next_prices.fillna(prices)).sum())
        records.append({
            "date": next_date,
            "portfolio_value": value,
            "cash": cash,
            "position_count": int((shares > 0).sum()),
        })

    equity = pd.DataFrame(records).set_index("date")
    bench = bench_close.reindex(equity.index).ffill()
    equity["benchmark_value"] = params.initial_cash * bench / bench.iloc[0]
    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1
    equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].iloc[0] - 1

    return equity, pd.DataFrame(target_rows)


def plot_returns(equity: pd.DataFrame, out_path: Path, strategy_label: str) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    (equity["strategy_return"] * 100).plot(ax=ax, label=f"{strategy_label} strategy", linewidth=2)
    (equity["benchmark_return"] * 100).plot(ax=ax, label="CSI 300 benchmark", linewidth=1.8)
    ax.set_title(f"{strategy_label} Strategy vs CSI 300")
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative return (%)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Qlib-integrated fundamental strategies")
    parser.add_argument("strategy", choices=["trend_serenity", "poe_pb_roe", "theme_etf_momentum"])
    parser.add_argument("--market", default="hs300")
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default=dt.date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--initial-cash", type=float, default=500_000.0)
    parser.add_argument("--factor-version", choices=["v1", "v2"], default="v2")
    parser.add_argument("--no-buffer", action="store_true", default=False)
    parser.add_argument("--experiment", choices=["v0", "v1", "v2", "v3"], default="v3")
    parser.add_argument("--theme-source", choices=["real_etf", "proxy_industry"], default="real_etf")
    parser.add_argument("--target-num", type=int, default=5)
    parser.add_argument("--etf-count", type=int, default=5)
    parser.add_argument("--no-moneyflow", action="store_true", default=False)
    parser.add_argument("--no-market-filter", action="store_true", default=False)
    args = parser.parse_args()

    if args.strategy == "theme_etf_momentum":
        from strategies.theme_etf_momentum import (
            ThemeETFParams,
            output_paths,
            run_theme_etf_backtest,
            summary_frame,
        )

        params = ThemeETFParams(
            initial_cash=args.initial_cash,
            benchmark=BENCHMARK,
            market=args.market,
            experiment=args.experiment,
            theme_source=args.theme_source,
            target_num=args.target_num,
            etf_count=args.etf_count,
            use_moneyflow=not args.no_moneyflow,
            market_filter=not args.no_market_filter,
        )
        equity, targets, themes = run_theme_etf_backtest(
            PROVIDER_URI,
            TOKEN_PATH,
            CACHE_DIR,
            args.market,
            args.start,
            args.end,
            params,
        )
        paths = output_paths(BASE_DIR / "outputs", args.market, args.start, args.end, args.experiment)
        equity.to_csv(paths["equity"])
        targets.to_csv(paths["targets"], index=False)
        themes.to_csv(paths["themes"], index=False)
        summary = summary_frame(equity, params)
        summary.to_csv(paths["summary"], index=False)
        plot_returns(equity, paths["plot"], f"Theme ETF Momentum {args.experiment.upper()}")

        print(f"\nTheme ETF Momentum {args.experiment.upper()} backtest summary")
        print(f"  theme_source: {args.theme_source}")
        for k, v in summary.iloc[0].items():
            if isinstance(v, (float, np.floating)):
                print(f"  {k}: {v:.4f}")
        print(f"\n  equity: {paths['equity']}")
        print(f"  targets: {paths['targets']}")
        print(f"  themes: {paths['themes']}")
        print(f"  summary: {paths['summary']}")
        print(f"  plot: {paths['plot']}")
        print("\nThis is not financial advice.")
        return

    equity, targets = run_manual_backtest(args.strategy, args)

    out_dir = BASE_DIR / "outputs"
    out_dir.mkdir(exist_ok=True)
    suffix = f"{args.market}_{pd.Timestamp(args.start):%Y%m%d}_{pd.Timestamp(args.end):%Y%m%d}"

    strategy_label = "Trend-Serenity" if args.strategy == "trend_serenity" else "POE PB+ROE"
    prefix = "trend_serenity" if args.strategy == "trend_serenity" else "poe_pb_roe"

    equity_path = out_dir / f"{prefix}_equity_{suffix}.csv"
    targets_path = out_dir / f"{prefix}_targets_{suffix}.csv"
    plot_path = out_dir / f"{prefix}_returns_{suffix}.png"
    equity.to_csv(equity_path)
    targets.to_csv(targets_path, index=False)
    plot_returns(equity, plot_path, strategy_label)

    from strategies._utils import summarize as summarizer
    print(f"\n{strategy_label} backtest summary")
    for k, v in summarizer(equity).items():
        print(f"  {k}: {v:.4f}")
    print(f"\n  equity: {equity_path}")
    print(f"  targets: {targets_path}")
    print(f"  plot: {plot_path}")
    print("\nThis is not financial advice.")


if __name__ == "__main__":
    main()
