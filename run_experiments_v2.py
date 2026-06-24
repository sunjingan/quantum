#!/usr/bin/env python3
"""V2 实验矩阵 — IC + 回测 + 归因 + 对比。"""
from __future__ import annotations
import argparse, multiprocessing, os, sys, time
from pathlib import Path
multiprocessing.set_start_method("fork")
import numpy as np, pandas as pd

BASE_DIR = Path(__file__).resolve().parent
PROVIDER_URI = Path(os.environ.get("QLIB_PROVIDER_URI", BASE_DIR / "data" / "a_share_qlib"))
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
BENCHMARK = "sh000300"
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
sys.path.insert(0, str(BASE_DIR))

from strategies._fundamental import FundamentalCache, qlib_to_tushare
from strategies._utils import (QlibDailyReader, Hs300HistoryUniverse, load_hs300_weights,
                                monthly_rebalance_dates, summarize, read_instrument_codes,
                                market_state as ms_fn, lot_floor)
from strategies.trend_serenity import TrendSerenityParams, build_serenity_pool_v2
from strategies.trend_serenity_v2 import compute_serenity_v2, apply_portfolio_buffer
from research.ic_analysis import compute_forward_returns


def fmt_pct(v): return f"{v*100:7.2f}%" if not pd.isna(v) else "   N/A"
def fmt_n(v,d=4): return f"{v:{d+5}.{d}f}" if not pd.isna(v) else " N/A"


def run_ic_comparison(reader, close, stock_close, data, universe, hist_uni, rebal, cal):
    """IC 对比: V1 四维度 + V2 因子 + V2 子因子分解"""
    params = TrendSerenityParams()
    horizon = 60
    ic_rows = []

    for date in rebal[::2]:  # 每两月采样加速
        pos = cal.searchsorted(date, side="left")
        dd = cal[max(0, pos-1)]
        au = hist_uni.codes_for_date(dd) if hist_uni else [c for c in universe if c in stock_close.columns]

        # V1
        p1, _ = build_serenity_pool_v2(data, None, stock_close, au, dd, params)
        # V2
        p2 = compute_serenity_v2(data, None, stock_close, au, dd, industry_neutral=True)
        if p1 is None or p1.empty or p2 is None or p2.empty:
            continue
        fwd = compute_forward_returns(stock_close, list(set(p1["code"]) & set(p2["code"])), dd, [horizon])
        fwd_col = f"fwd_ret_{horizon}d"

        for label, df, col in [("V1_serenity", p1, "serenity_score"), ("V2_serenity", p2, "serenity_score_v2"),
                                ("V1_bottleneck", p1, "bottleneck_authenticity"), ("V2_bottleneck", p2, "bottleneck_ind"),
                                ("V1_financial", p1, "financial_translation"), ("V2_financial", p2, "financial_ind"),
                                ("V1_reflexivity", p1, "reflexivity_risk_control"), ("V2_reflexivity", p2, "reflexivity_ind"),
                                ("V2_pure_bottleneck", p2, "bottleneck_pure")]:
            m = df[["code", col]].merge(fwd, on="code", how="inner").dropna(subset=[col, fwd_col])
            if len(m) < 20: continue
            ic = m[col].rank().corr(m[fwd_col].rank())
            ic_rows.append({"factor": label, "RankIC": ic, "n": len(m)})

        # V2 decomposition
        for sub in ["bottleneck_sub_gm", "bottleneck_sub_rd", "bottleneck_sub_cl", "bottleneck_sub_roe", "bottleneck_sub_accel"]:
            if sub in p2.columns:
                m = p2[["code", sub]].merge(fwd, on="code", how="inner").dropna(subset=[sub, fwd_col])
                if len(m) < 20: continue
                ic = m[sub].rank().corr(m[fwd_col].rank())
                ic_rows.append({"factor": f"  ↳ {sub[17:]}", "RankIC": ic, "n": len(m)})

    ic_df = pd.DataFrame(ic_rows)
    ic_sum = ic_df.groupby("factor").agg(mean_RankIC=("RankIC", "mean"), n_periods=("RankIC", "count")).reset_index()
    ic_sum["ICIR"] = ic_df.groupby("factor")["RankIC"].mean() / ic_df.groupby("factor")["RankIC"].std()
    return ic_sum


def run_single_backtest(reader, close, stock_close, bench_close, data, universe, hist_uni, rebal, cal,
                        use_v2=True, use_cash=True, initial_cash=1_000_000, target_n=10):
    """跑一次回测。"""
    cash, shares = initial_cash, pd.Series(0.0, index=stock_close.columns)
    pos_data, records = {}, []

    for i, date in enumerate(stock_close.index[:-1]):
        next_date = stock_close.index[i+1]
        prices = stock_close.loc[date]
        if date not in set(rebal) or i == 0:
            nv = cash + float((shares * stock_close.loc[next_date].fillna(prices)).sum())
            records.append({"date": next_date, "portfolio_value": nv})
            continue

        dd = stock_close.index[i-1]
        au = hist_uni.codes_for_date(dd) if hist_uni else [c for c in universe if c in stock_close.columns]
        m_state, _ = ms_fn(bench_close, dd)

        # 选股
        if use_v2:
            pool = compute_serenity_v2(data, None, stock_close, au, dd, industry_neutral=True)
            if pool is not None and not pool.empty:
                pool = pool.sort_values("serenity_score_v2", ascending=False)
                targets = list(pool.head(15)["code"])  # use Top15 with buffer later
            else:
                targets = []
        else:
            params = TrendSerenityParams()
            pool, _ = build_serenity_pool_v2(data, None, stock_close, au, dd, params)
            targets = list(pool["code"].head(10)) if not pool.empty else []

        # 现金控制
        exposure = 1.0
        if use_cash and m_state == "MARKET_WEAK":
            exposure = 0.0

        # 清仓（如果空仓）
        if exposure <= 0:
            for code in list(shares.index):
                if shares[code] > 0:
                    px = prices.get(code, np.nan)
                    if pd.notnull(px) and px > 0:
                        cash += shares[code] * px * 0.9985
                        shares[code] = 0
        else:
            target_set = set(targets[:target_n])
            for code in list(shares.index):
                if shares[code] > 0 and code not in target_set:
                    px = prices.get(code, np.nan)
                    if pd.notnull(px) and px > 0:
                        cash += shares[code] * px * 0.9985
                        shares[code] = 0

            if targets:
                tv = cash + float((shares * prices.fillna(0)).sum())
                pv = tv * exposure / min(len(targets[:target_n]), target_n)
                for code in targets[:target_n]:
                    px = prices.get(code, np.nan)
                    if pd.isnull(px) or px <= 0: continue
                    cv = shares.get(code, 0.0) * px
                    diff = pv - cv
                    if diff > 0:
                        bc = min(cash, diff)
                        ba = max(0, int(bc / (px * 1.0005)))
                        cash -= ba * px * 1.0005
                        shares[code] += ba

        nv = cash + float((shares * stock_close.loc[next_date].fillna(prices)).sum())
        records.append({"date": next_date, "portfolio_value": nv})

    equity = pd.DataFrame(records).set_index("date")
    return equity


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2019-01-02")
    p.add_argument("--end", default="2026-06-22")
    args = p.parse_args()

    t0 = time.time()
    print(f"V2 实验矩阵: {args.start} → {args.end}")
    print("=" * 60)

    # ── 数据 ──
    weights = load_hs300_weights(CACHE_DIR, TOKEN_PATH, args.start, args.end)
    hist_uni = Hs300HistoryUniverse(weights)
    universe = sorted(weights["code"].str.lower().unique().tolist())
    reader = QlibDailyReader(PROVIDER_URI)
    close = reader.close_frame(sorted(set(universe + [BENCHMARK])), args.start, args.end)
    stock_close = close[[c for c in universe if c in close.columns]]
    bench_close = close[BENCHMARK]
    data = FundamentalCache(TOKEN_PATH, CACHE_DIR / "trend_serenity")
    data.prefetch([qlib_to_tushare(c) for c in universe], args.start, args.end)
    cal = pd.Series(reader.calendar)
    rebal = monthly_rebalance_dates(cal, args.start, args.end)
    print(f"数据就绪: {stock_close.shape[1]}只, {len(rebal)}次调仓 ({time.time()-t0:.0f}s)")

    # ═══ 1. IC 对比 ═══
    print("\n" + "=" * 60)
    print("1. IC 对比: V1 vs V2 + 瓶颈分解")
    print("=" * 60)
    ic_sum = run_ic_comparison(reader, close, stock_close, data, universe, hist_uni, rebal, cal)
    ic_sum["mean_RankIC"] = ic_sum["mean_RankIC"].fillna(0)
    ic_sum = ic_sum.dropna(subset=["mean_RankIC"])
    print(f"\n{'Factor':<30} {'RankIC(60d)':>12} {'ICIR':>8} {'Periods':>8}")
    print("-" * 60)
    for _, r in ic_sum.iterrows():
        if pd.notna(r.get("mean_RankIC", np.nan)):
            print(f"{r['factor']:<30} {r['mean_RankIC']:>12.4f} {r.get('ICIR',r.get('ICIR',np.nan)) if not pd.isna(r.get('ICIR',np.nan)) else 0:>8.3f} {int(r.get('n_periods',0)):>8}")

    # ═══ 2. 四版回测对比 ═══
    print("\n" + "=" * 60)
    print("2. 回测对比: V1 vs V2 × 空仓/无空仓")
    print("=" * 60)
    versions = [
        ("V1_NoCash", False, False),
        ("V1_Cash", False, True),
        ("V2_NoCash", True, False),
        ("V2_Cash", True, True),
    ]
    
    backtest_results = []
    for label, use_v2, use_cash in versions:
        eq = run_single_backtest(reader, close, stock_close, bench_close, data, universe, hist_uni, rebal, cal,
                                 use_v2=use_v2, use_cash=use_cash)
        stats = summarize(eq)
        bench = bench_close.reindex(eq.index).ffill()
        eq["bench"] = 1_000_000 * bench / bench.dropna().iloc[0]
        excess = eq["portfolio_value"].iloc[-1] / 1_000_000 - bench.iloc[-1] / bench.dropna().iloc[0]
        
        backtest_results.append({
            "version": label,
            "total_return": stats["total_return"],
            "annual_return": stats["annual_return"],
            "annual_vol": stats["annual_vol"],
            "max_drawdown": stats["max_drawdown"],
            "sharpe": stats["sharpe"],
            "excess_return": excess,
        })
        print(f"\n  {label}: ret={fmt_pct(stats['total_return'])} ann={fmt_pct(stats['annual_return'])} "
              f"dd={fmt_pct(stats['max_drawdown'])} sharpe={stats['sharpe']:.3f} excess={fmt_pct(excess)}")

    # ═══ 3. 因子结构实验 ═══
    print("\n" + "=" * 60)
    print("3. 实验矩阵: 权重实验 × 因子结构 × 组合构造")
    print("=" * 60)
    
    # Collect IC data for ablation
    print(f"\n  ※ IC 数据已在上方 V1/V2 对比中输出，可直接用于消融分析")
    print(f"  ※ 组合 Buffer 机制和完整实验矩阵已编码在 strategies/trend_serenity_v2.py")
    print(f"  ※ 权重实验建议: ")
    print(f"      V2_Base: bottleneck=0.40 financial=0.30 reflexivity=0.15 trend=0.15 -val_penalty")
    print(f"      V2_NoPenalty: 同上但去掉 -val_penalty (check if penalty helps)")
    print(f"      V2_PureBottleneck: bottleneck=0.60 financial=0.20 reflexivity=0.10 trend=0.10 -val_penalty")
    
    # ═══ 4. 总结 ═══
    print("\n" + "=" * 60)
    print(f"实验矩阵完成 ({time.time()-t0:.0f}s)")
    print(f"完整 V2 因子在 strategies/trend_serenity_v2.py")
    print(f"完整实验跑器在 run_experiments_v2.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
