#!/usr/bin/env python3
"""F2_CAP_MA60 — 年度分段回测 + 月度表现分析 (修正版 v2)"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from run_multi_setting_pressure_tests import make_config, load_pit_pool, load_f2_pool
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts
from strategies.etf_loop_engine import EngineParams, run_and_save

OUT = BASE_DIR / "outputs" / "etf_loop"
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

FULL_EQUITY_PATH = OUT / "etf_loop_equity_ADJCORE_F2_CAP_MA60_OPEN_D1_h5_20130701_20260625.csv"

def pct(x): return "NA" if pd.isna(x) else f"{x*100:.2f}%"


def run_yearly(start: str, end: str) -> dict:
    year = start[:4]
    tag = f"VAL_YEAR_F2_CAP_MA60_{year}"
    pit = load_pit_pool(); f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2_orig = sorted(set(f2) | set(orig38))
    params = make_config("F2_CAP_MA60", pit, f2, f2_orig, tag, {}, start, end)
    params = EngineParams(**{**params.__dict__, "exp_tag": tag})

    sm = OUT / f"etf_loop_summary_{tag}_h{start.replace('-','')}_{end.replace('-','')}.csv"
    if sm.exists(): return pd.read_csv(sm).iloc[0].to_dict()
    eq, trades, audit = run_and_save(params, OUT)
    return audit["stats"]


def compute_monthly_from_equity(equity: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monthly returns and DD from equity curve (groupby year-month)."""
    df = equity.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    nav = df["portfolio_value"]

    # Group by year-month, get last NAV of each month
    grouped = nav.groupby([nav.index.year, nav.index.month])
    month_end = grouped.last()
    month_end.index = [f"{y}-{m:02d}-01" for y, m in month_end.index]
    month_end = pd.Series(month_end).sort_index()
    month_end.index = pd.to_datetime(month_end.index)

    # Monthly returns
    rets = month_end.pct_change().dropna()

    # Drawdown
    peak = nav.expanding().max()
    dd = nav / peak - 1.0

    # Build monthly return + DD table
    rows = []
    for idx, r in rets.items():
        y, m = idx.year, idx.month
        # DD at month end
        dd_at_m = dd.loc[idx.strftime('%Y-%m')] if hasattr(dd, 'loc') else float("nan")
        try:
            dd_v = float(dd.loc[str(idx.date())]) if str(idx.date()) in dd.index else float("nan")
        except:
            dd_v = 0.0
        rows.append({"year": y, "month": m, "return": float(r), "dd": float(dd_v)})
    monthly = pd.DataFrame(rows)

    # Annual stats from continuous curve (NAV ratio method)
    annual_rows = []
    for y in sorted(monthly["year"].unique()):
        yr_nav = nav[nav.index.year == y]
        if len(yr_nav) < 2: continue
        nav_start = yr_nav.iloc[0]
        nav_end = yr_nav.iloc[-1]
        total_ret = nav_end / nav_start - 1.0
        n_months = monthly[monthly["year"] == y].shape[0]
        ann_ret = (1 + total_ret) ** (12 / n_months) - 1 if n_months > 0 else 0.0
        # DD in year
        dd_yr = dd[dd.index.year == y].min() if len(dd) > 0 else 0.0
        annual_rows.append({
            "year": y, "annual_return": ann_ret, "total_return": total_ret,
            "max_drawdown": float(dd_yr),
            "nav_start": float(nav_start), "nav_end": float(nav_end)
        })
    annual_cont = pd.DataFrame(annual_rows)
    return monthly, annual_cont


def monthly_heatmap(monthly: pd.DataFrame, annual_cont: pd.DataFrame) -> str:
    """Monthly heatmap with continuous-curve annual returns."""
    ann_map = {int(r["year"]): r["annual_return"] for _, r in annual_cont.iterrows()}
    lines = ["## 3. 月度收益热力图（连续复利曲线）", "",
             "> 由 2013 年起连续复利曲线逐月计算，Annual 列为当年 NAV 比值年化",
             "",
             "| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | Annual |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for yr in sorted(monthly["year"].unique()):
        yr_data = monthly[monthly["year"] == yr].set_index("month")
        cells = []
        for m in range(1, 13):
            if m in yr_data.index:
                cells.append(f'{yr_data.loc[m,"return"]*100:+.1f}%')
            else:
                cells.append("—")
        ann = ann_map.get(yr, 0)
        cells.append(f"{ann*100:.1f}%")
        lines.append(f"| {yr} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main():
    print("=== F2_CAP_MA60 Annual + Monthly v2 ===")

    # ── 1. Load full equity, compute continuous monthly ──
    eq = pd.read_csv(FULL_EQUITY_PATH, parse_dates=["date"])
    monthly, annual_cont = compute_monthly_from_equity(eq)
    monthly_ps = monthly.groupby("month").agg(
        count=("return", "size"), avg_return=("return", "mean"),
        win_rate=("return", lambda x: (x > 0).sum() / len(x)),
        best=("return", "max"), worst=("return", "min")
    ).reset_index()
    print(f"Continuous: {len(monthly)} months, {len(annual_cont)} years")

    # ── 2. Annual separate backtests (independent yearly runs) ──
    yearly_stats = {}
    for y in range(2013, 2027):
        s = f"{y}-07-01" if y == 2013 else f"{y}-01-01"
        e = f"{y}-12-31" if y < 2026 else "2026-06-25"
        st = run_yearly(s, e)
        yearly_stats[y] = st
        print(f"  {y}: ann={pct(st.get('annual_return',0))}")

    # ── 3. Report ──
    L = [
        "# F2_CAP_MA60 年度分段回测 & 月度表现",
        "",
        "**配置**: F2_v3 核心池 + PIT capped 补漏 + MA60 过热惩罚, 佣金1bp + 滑点1bp",
        "**执行**: 信号日收盘打分 → 次日开盘成交",
        "",
        "---",
        "## 1. 年度独立回测 (每年重置 50 万, 独立运行)",
        "",
        "> ⚠️ 独立回测每年从空仓冷启动, 与连续复利曲线不同。连续曲线进入新年时已持有仓位, 收益通常更高",
        "",
        "| 年份 | 年化 | Sharpe | 最大回撤 | 总收益 | 最终资产 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for y in sorted(yearly_stats.keys()):
        s = yearly_stats[y]
        L.append(f"| {y} | {pct(s.get('annual_return',0))} | {s.get('sharpe_ratio',0):.2f} | "
                 f"{pct(s.get('max_drawdown',0))} | {pct(s.get('total_return',0))} | "
                 f"¥{s.get('final_value',0):,.0f} |")

    ann_vals = [s.get("annual_return", 0) for s in yearly_stats.values()]
    pos_years = sum(1 for v in ann_vals if v > 0)
    L += [
        "",
        "### 1.1 统计",
        f"- 年份: {len(yearly_stats)}, 正收益: {pos_years}/{len(ann_vals)}",
        f"- 最高: {pct(max(ann_vals))} ({sorted(yearly_stats.items(), key=lambda x: x[1].get('annual_return',0), reverse=True)[0][0]})",
        f"- 最低: {pct(min(ann_vals))} ({sorted(yearly_stats.items(), key=lambda x: x[1].get('annual_return',0))[0][0]})",
        f"- 平均: {pct(np.mean(ann_vals))}, 标准差: {pct(np.std(ann_vals))}",
        "",
    ]

    # ── 4. Continuous curve annual returns ──
    L += [
        "---",
        "## 2. 连续复利曲线年度收益 (2013 年起不重置)",
        "",
        "> 基于 ADJCORE_F2_CAP_MA60_OPEN_D1 连续复利曲线, 当年 NAV 比值年化",
        "",
        "| 年份 | 年化 | 总收益 | 最大回撤 | 年初NAV | 年末NAV |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, r in annual_cont.iterrows():
        L.append(f"| {int(r['year'])} | {pct(r['annual_return'])} | {pct(r['total_return'])} | "
                 f"{pct(r['max_drawdown'])} | ¥{r['nav_start']:,.0f} | ¥{r['nav_end']:,.0f} |")
    L.append("")

    # ── 5. Monthly heatmap ──
    L.append(monthly_heatmap(monthly, annual_cont))
    L.append("")

    # ── 6. Per-month stats ──
    L += [
        "---",
        "## 4. 各月份统计 (跨年汇总)",
        "",
        "| 月份 | 样本数 | 平均收益 | 胜率 | 最佳 | 最差 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, r in monthly_ps.iterrows():
        m_name = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(r["month"])]
        L.append(f"| {m_name} | {int(r['count'])} | {pct(r['avg_return'])} | {pct(r['win_rate'])} | "
                 f"{pct(r['best'])} | {pct(r['worst'])} |")
    L.append("")

    # ── 7. Worst/Best months ──
    for label, asc in [("5. 最差 10 个月", True), ("6. 最佳 10 个月", False)]:
        subset = monthly.sort_values("return", ascending=asc).head(10)
        L += ["---", f"## {label}", "", "| Year | Month | 收益 |", "|---|---:|---:|"]
        for _, r in subset.iterrows():
            m_name = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(r["month"])]
            L.append(f"| {int(r['year'])} | {m_name} | {pct(r['return'])} |")
        L.append("")

    # ── 8. Comparison note ──
    L += [
        "---",
        "## 7. 独立回测 vs 连续曲线差异说明",
        "",
        "每年独立回测（第1节）和连续复利曲线（第2-3节）的同年收益不同, 原因:",
        "",
        "- **仓位惯性**: 连续曲线跨年时保留上一年末的持仓(如2024底持有的白银LOF), 独立回测每年从空仓建仓",
        "- **冷启动成本**: 独立回测每年初需要重新建仓5个目标, 产生额外换手和滑点成本",
        "- **动量延续性**: 年底持仓往往正好是强动量标的, 年初惯性收益被独立回测的冷启动错过",
        "",
        "**建议**: 用连续曲线评估实际投资体验; 用独立回测评估策略在任意起点入场的稳健性",
    ]

    (REPORT_DIR / "annual_monthly_report.md").write_text("\n".join(L))
    monthly.to_csv(REPORT_DIR / "monthly_returns.csv", index=False)
    annual_cont.to_csv(REPORT_DIR / "annual_continuous_curve.csv", index=False)
    pd.DataFrame([{"year": y, **s} for y, s in yearly_stats.items()]).to_csv(
        REPORT_DIR / "annual_separate_backtests.csv", index=False)
    print(f"\nReport → {REPORT_DIR / 'annual_monthly_report.md'}")
    print("Done.")

if __name__ == "__main__":
    main()
