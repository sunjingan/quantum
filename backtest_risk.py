#!/usr/bin/env python3
"""风控对比回测 — 同一区间同时跑风控开/关，输出对比表"""
from __future__ import annotations
import argparse, multiprocessing, os, sys, time
from pathlib import Path
multiprocessing.set_start_method("fork")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, pandas as pd

BASE_DIR = Path(__file__).resolve().parent
PROVIDER_URI = Path(os.environ.get("QLIB_PROVIDER_URI", BASE_DIR / "data" / "a_share_qlib"))
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
OUT_DIR = BASE_DIR / "outputs"
BENCHMARK = "sh000300"
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
sys.path.insert(0, str(BASE_DIR))

from strategies._fundamental import FundamentalCache, qlib_to_tushare
from strategies._enrichment import EnrichmentCache
from strategies._utils import (QlibDailyReader, Hs300HistoryUniverse, load_hs300_weights,
                                lot_floor, monthly_rebalance_dates, summarize, read_instrument_codes,
                                market_state as market_state_fn)
from strategies.trend_serenity import (TrendSerenityParams, build_serenity_pool_v2,
                                        select_targets_v2, check_invalidation, price_strength_multi_mode)
from strategies._risk import (RiskParams, check_single_stop_loss,
                               check_portfolio_drawdown, compute_exposure_ratio,
                               filter_pool_by_risk, check_invalidation_enhanced)


def run_backtest(args, risk_enabled: bool) -> pd.DataFrame:
    """跑一次回测，返回 equity DataFrame"""
    params = TrendSerenityParams(initial_cash=args.initial_cash, target_num=args.target_num)
    risk = RiskParams() if risk_enabled else None
    label = "Risk-ON" if risk_enabled else "Risk-OFF"

    # ── universe + data loading (same as before) ──
    market = args.market.lower()
    if market in {"hs300", "csi300_history", "000300"}:
        weights = load_hs300_weights(CACHE_DIR, TOKEN_PATH, args.start, args.end)
        hist_uni = Hs300HistoryUniverse(weights)
        universe = sorted(weights["code"].str.lower().unique().tolist())
    else:
        universe = read_instrument_codes(PROVIDER_URI, market)
        hist_uni = None

    reader = QlibDailyReader(PROVIDER_URI)
    all_codes = sorted(set(universe + [BENCHMARK]))
    close = reader.close_frame(all_codes, args.start, args.end)
    stock_close = close[[c for c in universe if c in close.columns]]
    bench_close = close[BENCHMARK]
    if stock_close.empty:
        print(f"  {label}: ERROR - 无行情数据")
        return pd.DataFrame()

    data = FundamentalCache(TOKEN_PATH, CACHE_DIR / "trend_serenity")
    ts_uni = [qlib_to_tushare(c) for c in universe]
    data.prefetch(ts_uni, args.start, args.end)

    enrich = None
    if not args.skip_enrich:
        enrich = EnrichmentCache(TOKEN_PATH, CACHE_DIR)
        try:
            enrich.prefetch(ts_uni, args.start, args.end)
        except Exception:
            pass

    cal = pd.Series(reader.calendar)
    rebal = monthly_rebalance_dates(cal, args.start, args.end)

    cash = params.initial_cash
    shares = pd.Series(0.0, index=stock_close.columns)
    # Track per-position: (entry_price, highest_since_entry, entry_date)
    pos_data: dict[str, dict] = {}
    records = []
    equity_history = []  # for drawdown tracking

    for i, date in enumerate(stock_close.index[:-1]):
        next_date = stock_close.index[i + 1]
        prices = stock_close.loc[date]

        # ── daily: check stop-loss for all positions ──
        if risk_enabled and len(equity_history) > 0:
            for code in list(shares.index):
                if shares[code] <= 0 or code not in pos_data:
                    continue
                px = prices.get(code, np.nan)
                if pd.isnull(px) or px <= 0:
                    continue
                # Update highest since entry
                pos_data[code]["highest"] = max(pos_data[code]["highest"], px)
                should_sell, reason = check_single_stop_loss(
                    code, pos_data[code]["entry_price"], px,
                    pos_data[code]["highest"], risk
                )
                if should_sell:
                    cash += shares[code] * px * (1 - params.close_cost)
                    shares[code] = 0
                    del pos_data[code]
                    equity_history.append(f"{date.date()} STOP: {code} {reason}")

        # ── rebalance day? ──
        if date in set(rebal) and i > 0:
            data_date = stock_close.index[i - 1]
            if hist_uni is not None:
                au = hist_uni.codes_for_date(data_date)
            else:
                au = [c for c in universe if c in stock_close.columns]

            # Market state
            m_state, risk_state = market_state_fn(bench_close, data_date)

            # Portfolio drawdown
            current_value = cash + float((shares * prices.fillna(0)).sum())
            equity_history.append(current_value)
            eq_series = pd.Series([v for v in equity_history if isinstance(v, (int, float))])
            port_dd, should_reduce = check_portfolio_drawdown(eq_series, risk) if risk_enabled else (0.0, False)

            # Exposure ratio
            exposure = 1.0
            if risk_enabled:
                exposure = compute_exposure_ratio(m_state, risk_state, port_dd, risk)

            # Build pool
            try:
                pool, hard_excl = build_serenity_pool_v2(data, enrich, stock_close, au, data_date, params)
            except Exception:
                pool, hard_excl = pd.DataFrame(), pd.DataFrame()

            # Risk filters
            if risk_enabled and not pool.empty:
                pool = filter_pool_by_risk(pool, risk)

            targets = select_targets_v2(pool, params) if not pool.empty else []
            target_set = set(targets)

            # ── Invalidation / forced sells ──
            force_sell = set()
            for code in list(shares.index):
                if shares[code] <= 0:
                    continue
                px = prices.get(code, np.nan)
                if pd.isnull(px) or px <= 0:
                    continue
                if risk_enabled and code in pos_data:
                    # Enhanced invalidation
                    is_inv, reasons = check_invalidation_enhanced(
                        code, pos_data[code]["entry_price"], px,
                        pos_data[code]["highest"], pos_data[code]["entry_date"],
                        data_date, data, enrich, risk
                    )
                    if is_inv:
                        force_sell.add(code)
                        equity_history.append(f"{date.date()} INV: {code} {'; '.join(reasons)}")
                elif enrich is not None and code in pos_data:
                    # Basic invalidation
                    inv = check_invalidation(code, data, enrich, data_date, pos_data[code]["entry_date"])
                    if inv["invalidated"]:
                        force_sell.add(code)

            # Min hold protection
            if risk_enabled:
                for code in list(shares.index):
                    if shares[code] <= 0 or code in target_set or code in force_sell:
                        continue
                    if code in pos_data:
                        days_held = (date - pos_data[code]["entry_date"]).days
                        if days_held < risk.min_hold_days:
                            target_set.add(code)  # 保留，不卖出

            # Sell
            # 如果 exposure == 0，强制清仓所有持仓
            if risk_enabled and exposure <= 0:
                for code in list(shares.index):
                    if shares[code] <= 0:
                        continue
                    px = prices.get(code, np.nan)
                    if pd.notnull(px) and px > 0:
                        cash += shares[code] * px * (1 - params.close_cost)
                        shares[code] = 0
                    if code in pos_data:
                        del pos_data[code]
                # 跳过后续的正常卖出逻辑
                continue_sell = False
            else:
                continue_sell = True
            
            for code in list(shares.index):
                if shares[code] <= 0:
                    continue
                should_sell = code not in target_set or code in force_sell
                if risk_enabled and should_sell:
                    # Check portfolio drawdown reduction — skip selling if reducing exposure
                    if should_reduce and port_dd <= risk.max_portfolio_drawdown:
                        # Reduce positions proportionally instead of selling all
                        sell_ratio = 1 - risk.drawdown_reduce_exposure
                        sell_amt = shares[code] * sell_ratio
                        px = prices.get(code, np.nan)
                        if pd.notnull(px) and px > 0:
                            cash += sell_amt * px * (1 - params.close_cost)
                            shares[code] -= sell_amt
                        continue
                if not should_sell:
                    continue
                px = prices.get(code, np.nan)
                if pd.notnull(px) and px > 0:
                    cash += shares[code] * px * (1 - params.close_cost)
                    shares[code] = 0
                if code in pos_data:
                    del pos_data[code]

            # Buy (with exposure control)
            # 如果 exposure == 0，跳过买入（已在上面清仓）
            if exposure <= 0:
                targets = []
            
            if targets:
                tv = cash + float((shares * prices.fillna(0)).sum())
                effective_cash = cash * exposure
                n_targets = min(len(targets), risk.max_positions if risk_enabled else 99)
                pv = (cash * exposure + float((shares * prices.fillna(0)).sum())) / n_targets if n_targets > 0 else 0

                for code in targets[:n_targets]:
                    px = prices.get(code, np.nan)
                    if pd.isnull(px) or px <= 0:
                        continue
                    cv = shares.get(code, 0.0) * px
                    diff = pv - cv
                    if diff < 0:
                        sa = min(shares.get(code, 0.0), lot_floor(abs(diff) / px))
                        cash += sa * px * (1 - params.close_cost)
                        shares[code] -= sa
                    elif diff > 0:
                        bc = min(cash, diff)
                        ba = lot_floor(bc / (px * (1 + params.open_cost)))
                        cash -= ba * px * (1 + params.open_cost)
                        shares[code] += ba
                    if code not in pos_data:
                        pos_data[code] = {"entry_price": px, "highest": px, "entry_date": data_date}

        # Record
        nv = cash + float((shares * stock_close.loc[next_date].fillna(prices)).sum())
        records.append({
            "date": next_date, "portfolio_value": nv, "cash": cash,
            "position_count": int((shares > 0).sum()),
        })

    equity = pd.DataFrame(records).set_index("date")
    bench = bench_close.reindex(equity.index).ffill()
    fb = bench.dropna().iloc[0]
    equity["benchmark_value"] = params.initial_cash * bench / fb
    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1
    equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].iloc[0] - 1

    # Print summary
    stats = summarize(equity)
    print(f"\n  {'='*50}")
    print(f"  {label} 结果")
    print(f"  {'='*50}")
    print(f"  总收益: {stats['total_return']*100:.2f}%")
    print(f"  年化: {stats['annual_return']*100:.2f}%  波动: {stats['annual_vol']*100:.2f}%")
    print(f"  最大回撤: {stats['max_drawdown']*100:.2f}%  Sharpe: {stats['sharpe']:.3f}")
    print(f"  止损触发: {sum(1 for v in equity_history if isinstance(v, str) and 'STOP' in str(v))} 次")
    print(f"  失效卖出: {sum(1 for v in equity_history if isinstance(v, str) and 'INV' in str(v))} 次")
    print(f"  最终: {equity['portfolio_value'].iloc[-1]:,.0f} (CSI300: {equity['benchmark_value'].iloc[-1]:,.0f})")

    return equity


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2018-01-02")
    p.add_argument("--end", default="2026-06-22")
    p.add_argument("--market", default="hs300")
    p.add_argument("--target-num", type=int, default=10)
    p.add_argument("--initial-cash", type=float, default=1_000_000.0)
    p.add_argument("--skip-enrich", action="store_true", default=False)
    args = p.parse_args()

    print(f"风控对比回测: {args.start} — {args.end} 市场:{args.market}")
    print(f"富集数据: {'✓' if not args.skip_enrich else '✗'}")

    # 跑两遍
    t0 = time.time()
    eq_no_risk = run_backtest(args, risk_enabled=False)
    t1 = time.time()
    eq_risk = run_backtest(args, risk_enabled=True)
    t2 = time.time()

    if eq_no_risk.empty or eq_risk.empty:
        print("ERROR: 回测无结果"); return

    # ── 对比图 ──
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    # 收益曲线
    ((eq_no_risk["strategy_return"] + 1).cumprod() - 1).plot(ax=ax1, label="Risk-OFF", linewidth=1.5, alpha=0.8)
    ((eq_risk["strategy_return"] + 1).cumprod() - 1).plot(ax=ax1, label="Risk-ON", linewidth=2)
    ((eq_no_risk["benchmark_return"] + 1).cumprod() - 1).plot(ax=ax1, label="CSI300", linewidth=1, alpha=0.5, style="--")
    ax1.set_title("Cumulative Return")
    ax1.legend(); ax1.grid(True, alpha=0.3)

    # 回撤曲线
    dd_off = eq_no_risk["portfolio_value"] / eq_no_risk["portfolio_value"].cummax() - 1
    dd_on = eq_risk["portfolio_value"] / eq_risk["portfolio_value"].cummax() - 1
    (dd_off * 100).plot(ax=ax2, label="Risk-OFF", linewidth=1.5, alpha=0.8)
    (dd_on * 100).plot(ax=ax2, label="Risk-ON", linewidth=2)
    ax2.set_title("Drawdown")
    ax2.legend(); ax2.grid(True, alpha=0.3)
    ax2.set_ylabel("%")

    fig.tight_layout()
    s = f"risk_compare_{args.market}_{pd.Timestamp(args.start):%Y%m%d}_{pd.Timestamp(args.end):%Y%m%d}"
    pp = OUT_DIR / f"{s}.png"
    fig.savefig(pp, dpi=160); plt.close(fig)

    # ── 汇总对比表 ──
    s1 = summarize(eq_no_risk)
    s2 = summarize(eq_risk)
    print(f"\n{'='*60}")
    print(f"风控对比汇总")
    print(f"{'='*60}")
    print(f"{'指标':<20} {'Risk-OFF':>15} {'Risk-ON':>15} {'改善':>15}")
    print(f"{'-'*20} {'-'*15} {'-'*15} {'-'*15}")
    for k, label in [("total_return","总收益"),("annual_return","年化收益"),("annual_vol","年化波动"),
                     ("max_drawdown","最大回撤"),("sharpe","Sharpe")]:
        v1 = s1[k] * 100 if k != "sharpe" else s1[k]
        v2 = s2[k] * 100 if k != "sharpe" else s2[k]
        imp = v2 - v1
        sfx = "%" if k != "sharpe" else ""
        print(f"{label:<20} {v1:>14.2f}{sfx} {v2:>14.2f}{sfx} {imp:>+14.2f}{sfx}")
    print(f"\n对比图: {pp}")
    print(f"回测不构成投资建议。")


if __name__ == "__main__":
    main()
