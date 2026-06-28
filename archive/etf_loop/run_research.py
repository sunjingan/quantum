#!/usr/bin/env python3
"""
因子研究报告 — 六步分析框架，输出 10 张核心表。

用法:
  source activate.sh
  QLIB_PROVIDER_URI=data/a_share_qlib python archive/etf_loop/run_research.py \\
    --start 2019-01-02 --end 2026-06-22 --market hs300

输出目录: outputs/research/<timestamp>/
"""
from __future__ import annotations

import argparse, datetime as dt, json, multiprocessing, os, sys, time
from pathlib import Path
multiprocessing.set_start_method("fork")

import numpy as np, pandas as pd
from scipy import stats as sp_stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = PROJECT_ROOT
PROVIDER_URI = Path(os.environ.get("QLIB_PROVIDER_URI", BASE_DIR / "data" / "a_share_qlib"))
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
BENCHMARK = "sh000300"
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
sys.path.insert(0, str(PROJECT_ROOT))

from strategies._fundamental import FundamentalCache, qlib_to_tushare
from strategies._utils import (QlibDailyReader, Hs300HistoryUniverse, load_hs300_weights,
                                lot_floor, monthly_rebalance_dates, summarize,
                                read_instrument_codes, market_state as market_state_fn)
from strategies.trend_serenity import (TrendSerenityParams, build_serenity_pool_v2,
                                        select_targets_v2, check_invalidation)
from strategies.trend_serenity_v2 import compute_serenity_v2, select_serenity_v2_targets
from strategies._risk import (RiskParams, check_single_stop_loss,
                               check_portfolio_drawdown, compute_exposure_ratio,
                               filter_pool_by_risk, check_invalidation_enhanced)
from research.ic_analysis import run_ic_analysis


# ═══════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════

def fmt_pct(v):
    if pd.isna(v): return "  N/A"
    return f"{v*100:7.2f}%"

def fmt_float(v, d=2):
    if pd.isna(v): return "  N/A"
    return f"{v:{d+5}.{d}f}"


# ═══════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2019-01-02")
    p.add_argument("--end", default="2026-06-22")
    p.add_argument("--market", default="hs300")
    p.add_argument("--target-num", type=int, default=10)
    p.add_argument("--initial-cash", type=float, default=1_000_000.0)
    p.add_argument("--factor-version", choices=["v1", "v2"], default="v2")
    p.add_argument("--no-buffer", action="store_true", default=False)
    args = p.parse_args()

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = BASE_DIR / "outputs" / "research" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"研究报告输出目录: {out_dir}\n")

    t0 = time.time()
    params = TrendSerenityParams(
        initial_cash=args.initial_cash,
        target_num=args.target_num,
        factor_version=args.factor_version,
        use_buffer=not args.no_buffer,
    )
    score_col = "serenity_score_v2" if args.factor_version == "v2" else "serenity_score"

    # ── 1. 加载数据 ──
    print("=" * 60)
    print("1. 数据加载")
    print("=" * 60)
    market = args.market.lower()
    if market in {"hs300", "csi300_history", "000300"}:
        weights = load_hs300_weights(CACHE_DIR, TOKEN_PATH, args.start, args.end)
        hist_uni = Hs300HistoryUniverse(weights)
        universe = sorted(weights["code"].str.lower().unique().tolist())
    else:
        universe = read_instrument_codes(PROVIDER_URI, market)
        hist_uni = None
    print(f"  股票池: {len(universe)} 只")

    reader = QlibDailyReader(PROVIDER_URI)
    all_codes = sorted(set(universe + [BENCHMARK]))
    close = reader.close_frame(all_codes, args.start, args.end)
    stock_close = close[[c for c in universe if c in close.columns]]
    bench_close = close[BENCHMARK]
    print(f"  有效行情: {stock_close.shape[1]} 只 × {stock_close.shape[0]} 日")

    data = FundamentalCache(TOKEN_PATH, CACHE_DIR / "trend_serenity")
    ts_uni = [qlib_to_tushare(c) for c in universe]
    data.prefetch(ts_uni, args.start, args.end)
    print(f"  基础数据就绪 ({time.time()-t0:.0f}s)")

    # ── 2. IC 分析 ──
    print(f"\n{'='*60}")
    print(f"2. 因子有效性分析 (IC/RankIC/分组收益)")
    print(f"{'='*60}")
    ic = run_ic_analysis(
        PROVIDER_URI,
        TOKEN_PATH,
        CACHE_DIR,
        args.start,
        args.end,
        market=args.market,
        factor_version=args.factor_version,
    )
    ic_s = ic["ic_summary"]
    grp_s = ic["grouped_summary"]

    # 表1: IC 汇总
    print("\n┌─ 表1: 因子 IC 汇总 ─────────────────────────────────┐")
    print(f"│ {'Factor':<28} {'H':>4} {'mean_IC':>8} {'RankIC':>8} {'ICIR':>7} {'+ratio':>7} {'t_stat':>7} │")
    for _, r in ic_s.iterrows():
        print(f"│ {r['factor']:<28} {int(r['horizon']):>4} {r['mean_IC']:>8.4f} {r['mean_RankIC']:>8.4f} {r['ICIR']:>7.3f} {r['positive_ratio']:>7.3f} {r['t_stat']:>7.2f} │")
    print("└──────────────────────────────────────────────────────┘")
    ic_s.to_csv(out_dir / "1_ic_summary.csv", index=False)

    # 表2: 分组收益
    print(f"\n┌─ 表2: 分组收益 ({score_col}) ───────────────────┐")
    print(f"│ {'Group':<6} {'20d_fwd':>10} {'60d_fwd':>10} {'120d_fwd':>10} │")
    for h in [20, 60, 120]:
        for _, r in grp_s[grp_s["horizon"] == h].iterrows():
            print(f"│ {r['group']:<6} {r['mean_fwd_return']:>10.4f} {'':>10} {'':>10} │")
    print("└──────────────────────────────────────────────────────┘")
    grp_s.to_csv(out_dir / "2_grouped_returns.csv", index=False)

    # 表3: 消融实验 (四维度分别IC)
    print("\n┌─ 表3: 维度消融 (各维度独立 IC) ─────────────────────┐")
    dim_names = (
        ["bottleneck_ind", "financial_ind", "reflexivity_ind", "trend_confirm", "valuation_penalty", "bottleneck_pure"]
        if args.factor_version == "v2"
        else ["bottleneck_authenticity", "financial_translation", "expectation_gap", "reflexivity_risk_control"]
    )
    for fn in dim_names:
        sub = ic_s[ic_s["factor"] == fn]
        if not sub.empty:
            best = sub.loc[sub["mean_RankIC"].idxmax()]
            print(f"│ {fn:<35} best_h={int(best['horizon']):>3}d  RankIC={best['mean_RankIC']:>.4f}  ICIR={best['ICIR']:>.3f} │")
    print("└──────────────────────────────────────────────────────┘")

    # ── 3. 回测 + 风控 ──
    print(f"\n{'='*60}")
    print(f"3. 策略回测 (Risk-ON: 弱市空仓)")
    print(f"{'='*60}")
    risk = RiskParams()
    cal = pd.Series(reader.calendar)
    rebal = monthly_rebalance_dates(cal, args.start, args.end)

    cash, shares = params.initial_cash, pd.Series(0.0, index=stock_close.columns)
    pos_data, records, trade_records = {}, [], []
    equity_log = []

    for i, date in enumerate(stock_close.index[:-1]):
        next_date = stock_close.index[i + 1]
        prices = stock_close.loc[date]

        # daily stop check
        if len(equity_log) > 0:
            for code in list(shares.index):
                if shares[code] <= 0 or code not in pos_data:
                    continue
                px = prices.get(code, np.nan)
                if pd.isnull(px) or px <= 0:
                    continue
                pos_data[code]["highest"] = max(pos_data[code]["highest"], px)
                should_sell, reason = check_single_stop_loss(
                    code, pos_data[code]["entry_price"], px, pos_data[code]["highest"], risk)
                if should_sell:
                    cash += shares[code] * px * (1 - params.close_cost)
                    shares[code] = 0
                    del pos_data[code]

        if date in set(rebal) and i > 0:
            data_date = stock_close.index[i - 1]
            if hist_uni is not None:
                au = hist_uni.codes_for_date(data_date)
            else:
                au = [c for c in universe if c in stock_close.columns]

            m_state, risk_state = market_state_fn(bench_close, data_date)
            current_value = cash + float((shares * prices.fillna(0)).sum())
            equity_log.append(current_value)
            eq_series = pd.Series([v for v in equity_log if isinstance(v, (int, float))])
            port_dd, _ = check_portfolio_drawdown(eq_series, risk)
            exposure = compute_exposure_ratio(m_state, risk_state, port_dd, risk)

            # build pool
            try:
                if args.factor_version == "v2":
                    pool = compute_serenity_v2(
                        data,
                        None,
                        stock_close,
                        au,
                        data_date,
                        industry_neutral=params.industry_neutral_v2,
                    )
                    hard_excl = pd.DataFrame()
                else:
                    pool, hard_excl = build_serenity_pool_v2(data, None, stock_close, au, data_date, params)
            except Exception:
                pool, hard_excl = pd.DataFrame(), pd.DataFrame()

            if not pool.empty and args.factor_version == "v1":
                pool = filter_pool_by_risk(pool, risk)
            if not pool.empty and args.factor_version == "v2":
                current_holdings = set(shares[shares > 0].index)
                targets = select_serenity_v2_targets(
                    pool,
                    current_holdings=current_holdings if params.use_buffer else set(),
                    target_num=params.target_num,
                    buy_top_n=params.buy_top_n,
                    hold_threshold_n=params.hold_threshold_n if params.use_buffer else 0,
                    max_per_industry=params.max_per_industry,
                )
            else:
                targets = select_targets_v2(pool, params) if not pool.empty else []
            target_set = set(targets)

            # invalidation
            force_sell = set()
            for code in list(shares.index):
                if shares[code] <= 0 or code not in pos_data:
                    continue
                px = prices.get(code, np.nan)
                if pd.isnull(px) or px <= 0:
                    continue
                is_inv, reasons = check_invalidation_enhanced(
                    code, pos_data[code]["entry_price"], px,
                    pos_data[code]["highest"], pos_data[code]["entry_date"],
                    data_date, data, None, risk)
                if is_inv:
                    force_sell.add(code)

            # exposure=0 → clear all
            if exposure <= 0:
                for code in list(shares.index):
                    if shares[code] <= 0:
                        continue
                    px = prices.get(code, np.nan)
                    if pd.notnull(px) and px > 0:
                        cash += shares[code] * px * (1 - params.close_cost)
                        shares[code] = 0
                    if code in pos_data:
                        del pos_data[code]
            else:
                # normal sell
                for code in list(shares.index):
                    if shares[code] <= 0:
                        continue
                    if code not in target_set or code in force_sell:
                        px = prices.get(code, np.nan)
                        if pd.notnull(px) and px > 0:
                            cash += shares[code] * px * (1 - params.close_cost)
                            shares[code] = 0
                        if code in pos_data:
                            del pos_data[code]

            # buy
            if targets and exposure > 0:
                tv = cash + float((shares * prices.fillna(0)).sum())
                n_t = min(len(targets), risk.max_positions)
                pv = (cash * exposure + float((shares * prices.fillna(0)).sum())) / n_t if n_t > 0 else 0
                for code in targets[:n_t]:
                    px = prices.get(code, np.nan)
                    if pd.isnull(px) or px <= 0:
                        continue
                    cv = shares.get(code, 0.0) * px
                    diff = pv - cv
                    if diff < 0:
                        sa = min(shares.get(code, 0.0), int(abs(diff) / px))
                        cash += sa * px * (1 - params.close_cost)
                        shares[code] -= sa
                    elif diff > 0:
                        bc = min(cash, diff)
                        ba = int(bc / (px * (1 + params.open_cost)))
                        cash -= ba * px * (1 + params.open_cost)
                        shares[code] += ba
                    if code not in pos_data:
                        pos_data[code] = {"entry_price": px, "highest": px, "entry_date": data_date}

            # record trades
            for rank, code in enumerate(targets, start=1):
                rd = {"date": date, "rank": rank, "code": code}
                if not pool.empty and code in pool["code"].values:
                    r = pool[pool["code"] == code].iloc[0].to_dict()
                    for k in ["name", "industry_name", "tier", "serenity_score", "serenity_score_v2",
                              "bottleneck_authenticity", "financial_translation",
                              "expectation_gap", "reflexivity_risk_control",
                              "bottleneck_ind", "financial_ind", "reflexivity_ind",
                              "trend_confirm", "valuation_penalty", "bottleneck_pure",
                              "q_sales_yoy", "gross_margin", "pe_ttm", "price_score"]:
                        if k in r:
                            rd[k] = r[k]
                trade_records.append(rd)

        # record equity
        nv = cash + float((shares * stock_close.loc[next_date].fillna(prices)).sum())
        records.append({"date": next_date, "portfolio_value": nv, "cash": cash,
                        "position_count": int((shares > 0).sum())})

    # ── 4. 回测结果 ──
    equity = pd.DataFrame(records).set_index("date")
    trades = pd.DataFrame(trade_records)
    bench = bench_close.reindex(equity.index).ffill()
    fb = bench.dropna().iloc[0]
    equity["benchmark_value"] = params.initial_cash * bench / fb
    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1
    equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].iloc[0] - 1
    stats = summarize(equity)
    equity.to_csv(out_dir / "equity_curve.csv")
    trades.to_csv(out_dir / "trade_records.csv", index=False)

    # 表4: 年度表现
    print(f"\n┌─ 表4: 年度表现 ────────────────────────────────────┐")
    print(f"│ {'Year':<6} {'Strategy':>9} {'Benchmark':>9} {'Excess':>9} {'MaxDD':>8} {'Turnover':>8} │")
    equity["year"] = equity.index.year
    for yr, grp in equity.groupby("year"):
        ret_s = grp["portfolio_value"].iloc[-1] / grp["portfolio_value"].iloc[0] - 1
        ret_b = grp["benchmark_value"].iloc[-1] / grp["benchmark_value"].iloc[0] - 1
        dd = (grp["portfolio_value"] / grp["portfolio_value"].cummax() - 1).min()
        print(f"│ {yr:<6} {fmt_pct(ret_s)} {fmt_pct(ret_b)} {fmt_pct(ret_s-ret_b)} {fmt_pct(dd)} {'  N/A':>8} │")
    print("└──────────────────────────────────────────────────────┘")

    # 表5: 市场状态表现
    print(f"\n┌─ 表5: 市场状态表现 ────────────────────────────────┐")
    print(f"│ {'Regime':<15} {'Days':>6} {'Strategy':>9} {'Bench':>9} {'Excess':>9} │")
    for state_name, state_val in [("STRONG","MARKET_STRONG"), ("WEAK","MARKET_WEAK"), ("NEUTRAL","MARKET_NEUTRAL")]:
        regime_dates = []
        for d in equity.index:
            dd = pd.Timestamp(str(d)) - pd.Timedelta(days=1)
            ms, _ = market_state_fn(bench_close, dd)
            if ms == state_val:
                regime_dates.append(d)
        if regime_dates:
            rg = equity.loc[regime_dates]
            if len(rg) > 1:
                ret_s = rg["portfolio_value"].iloc[-1] / rg["portfolio_value"].iloc[0] - 1
                ret_b = rg["benchmark_value"].iloc[-1] / rg["benchmark_value"].iloc[0] - 1
                print(f"│ {state_name:<15} {len(rg):>6} {fmt_pct(ret_s)} {fmt_pct(ret_b)} {fmt_pct(ret_s-ret_b)} │")
    print("└──────────────────────────────────────────────────────┘")

    # 表6: 行业归因
    print(f"\n┌─ 表6: 行业归因 (Top 10 行业) ─────────────────────┐")
    print(f"│ {'Industry':<20} {'Count':>6} {'Avg_Score':>10} │")
    if not trades.empty and "industry_name" in trades.columns and score_col in trades.columns:
        ind = trades.groupby("industry_name").agg(
            count=("code", "count"),
            avg_score=(score_col, "mean")
        ).sort_values("count", ascending=False).head(10)
        for idx, r in ind.iterrows():
            print(f"│ {str(idx)[:20]:<20} {int(r['count']):>6} {r['avg_score']:>10.4f} │")
    print("└──────────────────────────────────────────────────────┘")

    # 表7: 个股归因 (Top 10 贡献)
    print(f"\n┌─ 表7: 个股归因 (Top 10 被选中次数) ──────────────┐")
    print(f"│ {'Code':<12} {'Name':<12} {'Times':>6} {'Avg_Score':>10} │")
    if not trades.empty and score_col in trades.columns:
        stk = trades.groupby("code").agg(
            times=("date", "count"),
            avg_score=(score_col, "mean"),
            name=("name", "first")
        ).sort_values("times", ascending=False).head(10)
        for idx, r in stk.iterrows():
            print(f"│ {idx:<12} {str(r.get('name',''))[:12]:<12} {int(r['times']):>6} {r['avg_score']:>10.4f} │")
    print("└──────────────────────────────────────────────────────┘")

    # ── 5. 成本分析 ──
    print(f"\n{'='*60}")
    print(f"5. 成本和换手分析")
    print(f"{'='*60}")
    # 表8: 成本敏感性
    print(f"\n┌─ 表8: 成本压力测试 ────────────────────────────────┐")
    print(f"│ {'BuyCost':>8} {'SellCost':>9} {'AnnRet':>9} {'MaxDD':>8} {'Sharpe':>7} │")
    cost_pairs = [(0.0005, 0.0015), (0.001, 0.002), (0.002, 0.003), (0.003, 0.005), (0.005, 0.008)]
    for bc, sc in cost_pairs:
        # 简化重跑 (用之前的结果 * 扣减)
        cost_adj = 1 - (bc + sc) * 12  # 月度调仓 × 往返成本
        adj_ret = stats["annual_return"] - (bc + sc) * 12 / 2
        print(f"│ {bc*100:>7.2f}% {sc*100:>8.2f}% {fmt_pct(adj_ret)} {fmt_pct(stats['max_drawdown'])} {stats['sharpe']:>7.3f} │")
    print("└──────────────────────────────────────────────────────┘")

    # 表9: 换手率
    print(f"\n┌─ 表9: 换手率统计 ──────────────────────────────────┐")
    print(f"│ 月度调仓 | turnover tracking TBD                     │")
    print("└──────────────────────────────────────────────────────┘")

    # ── 6. 基本面一致性 ──
    print(f"\n{'='*60}")
    print(f"6. 基本面一致性")
    print(f"{'='*60}")
    print(f"\n┌─ 表10: 基本面一致性 (最近5次调仓) ──────────────────┐")
    recent = trades["date"].unique()[-5:] if not trades.empty else []
    for d in recent:
        sub = trades[trades["date"] == d].head(5)
        codes = ", ".join([f"{r['code']}({r.get('name','?')})" for _, r in sub.iterrows()])
        print(f"│ {d}: {codes[:70]}")
    print("└──────────────────────────────────────────────────────┘")

    # ── 总结 ──
    print(f"\n{'='*60}")
    print(f"研究完成 — 输出目录: {out_dir}")
    print(f"总耗时: {time.time()-t0:.0f}s")
    print(f"文件: 1_ic_summary.csv, 2_grouped_returns.csv, equity_curve.csv, trade_records.csv")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
