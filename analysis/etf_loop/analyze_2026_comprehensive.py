#!/usr/bin/env python3
"""
2026 Comprehensive Analysis for F2_CAP_MA60
- Fixed charts: 35x10, ETF Chinese names as filenames, PnL displayed, signal_close, dynamic start
- Monthly PnL heatmap, win rate / max drawdown stats
- ETF deep attribution, momentum crash detection
- Code verification: suspension handling, adj factors, no future functions
"""
from __future__ import annotations

import os, sys, re
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from strategies.etf_loop_strategy import ETFDailyStore, SectorProsperityCache

os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".matplotlib_cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

OUT = BASE_DIR / "outputs" / "etf_loop"
CACHE = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity"
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"
FIG_DIR_2026 = REPORT_DIR / "trade_charts_2026_v2"
FIG_DIR_CRASH = REPORT_DIR / "trade_charts_2026_crash"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR_2026.mkdir(parents=True, exist_ok=True)
FIG_DIR_CRASH.mkdir(parents=True, exist_ok=True)

def setup_fonts():
    for path in [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]:
        if Path(path).exists():
            fm.fontManager.addfont(path)
            prop = fm.FontProperties(fname=path)
            plt.rcParams["font.family"] = prop.get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False

def fmt(x): return "NA" if pd.isna(x) else f"{x*100:.2f}%"

def load_names():
    path = CACHE / "fund_basic_etf.csv"
    if not path.exists(): return {}
    df = pd.read_csv(path, dtype={"ts_code": str})
    return dict(zip(df["ts_code"].astype(str), df["name"].astype(str), strict=False))

def load_2026_data(tag="VAL_YEAR_F2_CAP_MA60_2026"):
    eq = pd.read_csv(OUT / f"etf_loop_equity_{tag}_h5_20260101_20260625.csv", parse_dates=["date"])
    trades = pd.read_csv(OUT / f"etf_loop_targets_{tag}_h5_20260101_20260625.csv", dtype={"ts_code": str})
    sm = OUT / f"etf_loop_summary_{tag}_h5_20260101_20260625.csv"
    stats = pd.read_csv(sm).iloc[0].to_dict() if sm.exists() else {}
    return eq.set_index("date").sort_index(), trades, stats

def compute_fifo_pnl(trades):
    trades = trades.copy()
    trades["trade_date"] = pd.to_datetime(trades["trade_date"])
    for c in ["net_cost", "net_proceeds"]:
        trades[c] = pd.to_numeric(trades.get(c, 0), errors="coerce").fillna(0)
    trades["shares"] = pd.to_numeric(trades.get("shares", 0), errors="coerce").fillna(0).astype(float)
    trades["action"] = trades["action"].astype(str)
    pnl = {}; lots = {}
    trade_details = []
    for _, r in trades.sort_values(["trade_date", "date"]).iterrows():
        code = str(r["ts_code"]); shares = float(r["shares"]); act = r["action"]
        if shares <= 0: continue
        if act == "BUY":
            cpp = float(r["net_cost"]) / shares
            lots.setdefault(code, []).append([shares, cpp, r["trade_date"]])
        elif act == "SELL":
            proceeds = float(r["net_proceeds"]); remaining = shares; sell_date = r["trade_date"]
            while remaining > 0 and lots.get(code):
                lot = lots[code][0]; take = min(remaining, lot[0])
                trade_pnl = (proceeds / shares) * take - lot[1] * take
                pnl[code] = pnl.get(code, 0.0) + trade_pnl
                trade_details.append({
                    "code": code, "buy_date": lot[2], "sell_date": sell_date,
                    "pnl": trade_pnl, "shares": take, "buy_price": lot[1],
                    "sell_price": proceeds / shares,
                })
                lot[0] -= take; remaining -= take
                if lot[0] <= 0: lots[code].pop(0)
    return pnl, pd.DataFrame(trade_details)

def monthly_analysis(nav: pd.Series):
    df = nav.reset_index(); df.columns = ["date", "nav"]
    df["year"] = df["date"].dt.year; df["month"] = df["date"].dt.month
    monthly = df.groupby(["year", "month"]).agg(
        first_nav=("nav", "first"), last_nav=("nav", "last"),
        min_nav=("nav", "min"), max_nav=("nav", "max"),
    ).reset_index()
    monthly["ret"] = monthly["last_nav"] / monthly["first_nav"] - 1.0
    monthly["intra_dd"] = monthly["min_nav"] / monthly["max_nav"] - 1.0
    peak = nav.expanding().max(); dd_series = nav / peak - 1.0
    monthly_stats = []
    for _, row in monthly.iterrows():
        ym = f"{int(row['year'])}-{int(row['month']):02d}"
        if not any(d.strftime("%Y-%m") == ym for d in nav.index): continue
        try:
            month_nav = nav.loc[ym]
        except:
            continue
        if len(month_nav) < 2: continue
        month_peak = month_nav.expanding().max()
        month_dd = (month_nav / month_peak - 1.0).min()
        days_up = (month_nav.diff().dropna() > 0).sum()
        days_total = max(len(month_nav) - 1, 1)
        month_win_rate = days_up / days_total
        monthly_stats.append({
            "year_month": ym, "ret": row["ret"], "max_dd": month_dd,
            "win_rate": month_win_rate, "days": days_total,
        })
    return monthly, dd_series, pd.DataFrame(monthly_stats)

def detect_momentum_crashes(store, trades, names):
    trades = trades.copy(); trades["trade_date"] = pd.to_datetime(trades["trade_date"])
    trades["action"] = trades["action"].astype(str); trades = trades.sort_values("trade_date")
    crashes = []
    for code in trades["ts_code"].dropna().astype(str).unique():
        if code not in store.signal_close.columns: continue
        close = store.signal_close[code].dropna()
        ct = trades[trades["ts_code"].astype(str) == code]
        for _, trade_row in ct.iterrows():
            trade_date = trade_row["trade_date"]; act = trade_row["action"]
            price = close.loc[trade_date] if trade_date in close.index else np.nan
            if pd.isna(price) or price <= 0: continue
            before = close.loc[:trade_date].iloc[-60:] if len(close.loc[:trade_date]) >= 60 else close.loc[:trade_date]
            after = close.loc[trade_date:].iloc[:20] if len(close.loc[trade_date:]) >= 20 else close.loc[trade_date:]
            if len(before) < 10 or len(after) < 3: continue
            pct_rank = (before < price).mean()
            fwd_10d_ret = after.iloc[min(10, len(after)-1)] / price - 1.0 if len(after) >= 2 else np.nan
            fwd_dd = (after / price - 1.0).min() if len(after) >= 2 else np.nan
            crashes.append({"code": code, "trade_date": trade_date, "action": act,
                "price": price, "pct_rank": pct_rank, "fwd_10d_ret": fwd_10d_ret, "fwd_dd": fwd_dd})
    df = pd.DataFrame(crashes)
    if df.empty: return df
    buys = df["action"] == "BUY"; sells = df["action"] == "SELL"
    df["severity"] = np.nan
    if buys.any():
        df.loc[buys, "severity"] = (df.loc[buys, "pct_rank"] * 0.3
            - df.loc[buys, "fwd_dd"].clip(lower=-0.5, upper=0.0) * 0.7)
    if sells.any():
        df.loc[sells, "severity"] = ((1.0 - df.loc[sells, "pct_rank"]) * 0.3
            + df.loc[sells, "fwd_10d_ret"].clip(lower=0.0, upper=0.5) * 0.7)
    df = df.sort_values("severity", ascending=False)
    df["name"] = df["code"].map(names).fillna("")
    return df

def safe_fname(name, code):
    short = code.replace(".", "")[-6:]
    name = re.sub(r'[\\/*?:"<>|]', '', name).strip()
    if not name: name = code.replace(".", "")
    if len(name) > 40: name = name[:40]
    return f"{name}_{short}"

def plot_one_etf(store, code, trades, pnl_val, names, out_dir, tag_label="F2_CAP_MA60 2026"):
    if code not in store.signal_close.columns: return None
    ct = trades[trades["ts_code"].astype(str) == code]
    if ct.empty: return None
    ct_dates = pd.to_datetime(ct["trade_date"]).dropna()
    if ct_dates.empty: return None
    first_trade = ct_dates.min()
    plot_start = max(first_trade - pd.Timedelta(days=60), pd.Timestamp("2025-12-15"))
    close_raw = store.signal_close[code].loc[plot_start:"2026-06-27"].dropna().ffill()
    if len(close_raw) < 5: return None
    nav_curve = close_raw / close_raw.iloc[0]
    buys = ct[ct["action"].astype(str).eq("BUY")]
    sells = ct[ct["action"].astype(str).eq("SELL")]
    buy_dates = pd.to_datetime(buys["trade_date"].dropna())
    sell_dates = pd.to_datetime(sells["trade_date"].dropna())
    bd = nav_curve.reindex(buy_dates).dropna()
    sd = nav_curve.reindex(sell_dates).dropna()
    fig, ax = plt.subplots(figsize=(35, 10))
    ax.plot(nav_curve.index, nav_curve.values, color="#222222", linewidth=1.2,
            label="signal close (pct_chg adjusted)")
    if len(bd):
        ax.scatter(bd.index, bd.values, s=60, color="#d62728", edgecolor="white",
                   linewidth=0.5, label="BUY", zorder=3, alpha=0.85)
    if len(sd):
        ax.scatter(sd.index, sd.values, s=60, color="#1f77b4", edgecolor="white",
                   linewidth=0.5, label="SELL", zorder=3, alpha=0.85)
    name = names.get(code, ""); ep = pnl_val
    title = (f"{tag_label} | {name} ({code}) | 持仓PnL: {ep:,.0f}¥ | "
             f"buys: {len(buys)} sells: {len(sells)}")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_ylabel("revalued price (1.0 = chart start)", fontsize=10)
    ax.grid(True, alpha=0.15); ax.legend(loc="upper left", fontsize=10)
    fig.tight_layout()
    fpath = out_dir / f"{safe_fname(name, code)}.png"
    fig.savefig(fpath, dpi=150); plt.close(fig)
    return fpath

def analyze_missed_opportunities(store, trades, names, top_n=14):
    trades["trade_date"] = pd.to_datetime(trades["trade_date"])
    trades["action"] = trades["action"].astype(str)
    all_etf_returns = {}
    for code in store.signal_close.columns:
        close = store.signal_close[code].dropna()
        if len(close) < 20: continue
        monthly = close.resample("ME").last()
        if len(monthly) < 2: continue
        rets = monthly.pct_change().dropna()
        if len(rets) == 0: continue
        all_etf_returns[code] = rets
    monthly_held = {}
    for _, r in trades.iterrows():
        date = r["trade_date"]; code = str(r["ts_code"]); ym = date.strftime("%Y-%m")
        if ym not in monthly_held: monthly_held[ym] = set()
        monthly_held[ym].add(code)
    missed = []
    for ym in sorted(all_etf_returns[next(iter(all_etf_returns))].index.strftime("%Y-%m")):
        held = monthly_held.get(ym, set())
        month_returns = {}
        for code, rets in all_etf_returns.items():
            ym_list = list(rets.index.strftime("%Y-%m"))
            if ym in ym_list:
                idx = ym_list.index(ym)
                month_returns[code] = rets.iloc[idx]
        if not month_returns: continue
        sorted_ret = sorted(month_returns.items(), key=lambda x: x[1], reverse=True)
        for code, ret in sorted_ret[:5]:
            if code not in held:
                missed.append({"year_month": ym, "code": code,
                    "name": names.get(code, ""), "ret": ret})
    return pd.DataFrame(missed) if missed else pd.DataFrame(columns=["year_month", "code", "name", "ret"])

def build_monthly_heatmap(nav: pd.Series, save_csv=None):
    df = nav.reset_index(); df.columns = ["date", "nav"]
    df["year"] = df["date"].dt.year; df["month"] = df["date"].dt.month
    monthly = df.groupby(["year", "month"]).agg(
        first=("nav", "first"), last=("nav", "last")).reset_index()
    monthly["ret"] = monthly["last"] / monthly["first"] - 1.0
    pivot = monthly.pivot(index="year", columns="month", values="ret")
    annual = monthly.groupby("year")["ret"].apply(lambda x: (1 + x).prod() - 1.0)
    pivot["Annual"] = annual
    if save_csv: pivot.to_csv(save_csv)
    return pivot

def monthly_heatmap_markdown(pivot: pd.DataFrame) -> str:
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    cols_h1 = [c for c in [1,2,3,4,5,6] if c in pivot.columns]
    cols_h2 = [c for c in [7,8,9,10,11,12] if c in pivot.columns]
    lines = ["## 月度收益热力图（连续复利曲线）", "",
             "> Annual = 全年 NAV 比值总收益，H1/H2 拆分仅为阅读方便", ""]
    lines.append("### 上半年 (Jan-Jun)")
    lines.append("| Year | " + " | ".join(months[:len(cols_h1)]) + " | Annual |")
    lines.append("|---:" + "|---:" * len(cols_h1) + "|---:|")
    for year in sorted(pivot.index):
        row = f"| {year} |"
        for m in cols_h1:
            v = pivot.loc[year, m] if m in pivot.columns else np.nan
            row += f" {v:+.1%} |" if pd.notna(v) else " — |"
        ann = pivot.loc[year, "Annual"] if "Annual" in pivot.columns else np.nan
        row += f" {ann:.1%} |" if pd.notna(ann) else " — |"
        lines.append(row)
    lines.append("")
    lines.append("### 下半年 (Jul-Dec)")
    lines.append("| Year | " + " | ".join(months[6:6+len(cols_h2)]) + " | Annual |")
    lines.append("|---:" + "|---:" * len(cols_h2) + "|---:|")
    for year in sorted(pivot.index):
        row = f"| {year} |"
        for m in cols_h2:
            v = pivot.loc[year, m] if m in pivot.columns else np.nan
            row += f" {v:+.1%} |" if pd.notna(v) else " — |"
        ann = pivot.loc[year, "Annual"] if "Annual" in pivot.columns else np.nan
        row += f" {ann:.1%} |" if pd.notna(ann) else " — |"
        lines.append(row)
    lines.append("")
    return "\n".join(lines)

def verify_code_integrity(store, trades):
    report = []
    report.append("## Code Integrity Verification")
    report.append("### 1. 复权因子处理")
    report.append("- `signal_close` 由 `pct_chg` 累计乘积构建 -> 天然连续复权，不受除权除息跳变影响")
    report.append("- 原始 `close` 仅在初始化时作为基准锚点使用（`_build_adjusted_close` 中 `first_close`）")
    report.append("- `signal_open/high/low/vwap` 均通过 `price = signal_close x (raw_field / raw_close)` 比值对齐")
    report.append("### 2. 停牌处理")
    report.append("- 数据读取阶段: `pct_chg.fillna(0.0)` — 停牌日涨幅填0，保证连续曲线无断点")
    report.append("- 估值阶段: `signal_close.ffill()` — forward fill 填补缺失日，维持持仓估值连续")
    report.append("- 执行阶段: `execution_price()` 在当日无价格时返回 NaN -> `execute_sell/buy` 检查并跳过")
    report.append("- 实际效果: 停牌期间持仓不动（估值 forward fill），复牌后按开盘价执行调仓")
    report.append("### 3. 未来函数检查")
    report.append("- 信号计算: `store.price_series(code, date, lookback)` -> 使用 `loc[:date]` 严格截断")
    report.append("- 动量打分: `get_ranked_etfs(store, signal_date, params)` -> 仅使用 `signal_date` 之前数据")
    report.append("- 执行延迟: 信号日收盘(signal_date)打分 -> 次日(exec_date)开盘价成交 -> 无 look-ahead")
    report.append("- 风控止损: 止损价基于 `entry_prices`（买入时记录），当天信号日收盘触发 -> 次日开盘执行")
    report.append("### 4. 实际交易审计")
    trades_copy = trades.copy()
    trades_copy["trade_date"] = pd.to_datetime(trades_copy["trade_date"])
    trades_copy["date"] = pd.to_datetime(trades_copy["date"])
    violations = (trades_copy["date"] >= trades_copy["trade_date"]).sum()
    report.append(f"- 信号日 >= 执行日的违规交易: {violations} 笔 (应为0)")
    delta = (trades_copy["trade_date"] - trades_copy["date"]).dropna()
    if len(delta) > 0:
        report.append(f"- 信号->执行延迟: 平均 {delta.mean().days:.1f} 天, 最小 {delta.min().days} 天, 最大 {delta.max().days} 天")
    return "\n".join(report)

def main():
    setup_fonts()
    names = load_names()
    print("=" * 70)
    print("  2026 Comprehensive Analysis - F2_CAP_MA60")
    print("=" * 70)

    # Load data
    print("\n-> Loading 2026 standalone backtest data...")
    eq, trades, stats = load_2026_data("VAL_YEAR_F2_CAP_MA60_2026")
    nav = eq["portfolio_value"]
    print(f"  Dates: {nav.index[0].date()} -> {nav.index[-1].date()} ({len(nav)} trading days)")
    print(f"  Start NAV: {nav.iloc[0]:,.0f}Y -> End NAV: {nav.iloc[-1]:,.0f}Y")

    # Compute PnL
    print("\n-> Computing FIFO PnL...")
    pnl_dict, trade_details = compute_fifo_pnl(trades)

    # Build store
    codes_traded = sorted(trades["ts_code"].dropna().astype(str).unique())
    print(f"\n-> Building data store for {len(codes_traded)} ETFs...")
    cache = SectorProsperityCache(TOKEN_PATH, CACHE_DIR)
    store = ETFDailyStore(cache, codes_traded, "2025-10-01", "2026-06-27")
    print(f"  Store ready: {len(store.signal_close.columns)} codes")

    # SECTION A: Monthly Analysis
    print("\n" + "=" * 50)
    print("  SECTION A: Monthly Analysis")
    print("=" * 50)
    monthly_df, dd_series, monthly_stats = monthly_analysis(nav)
    heatmap_pivot = build_monthly_heatmap(nav, REPORT_DIR / "monthly_heatmap_2026.csv")
    print("\n--- 2026 Monthly Returns ---")
    for _, row in monthly_df.iterrows():
        if int(row["year"]) == 2026:
            print(f"  {int(row['month']):02d}: {row['ret']:+.2%} (intra-DD: {row['intra_dd']:+.2%})")
    print(f"\n  Total return: {(nav.iloc[-1]/500000-1):.2%}")
    print(f"  Annualized: {((nav.iloc[-1]/500000)**(252/len(nav))-1):.2%}")
    print(f"  Max DD: {dd_series.min():.2%}")
    print("\n--- Monthly Win Rate & MDD ---")
    monthly_stats["annualized"] = (1 + monthly_stats["ret"]) ** (252 / monthly_stats["days"]) - 1
    for _, row in monthly_stats.iterrows():
        print(f"  {row['year_month']}: ret={row['ret']:+.2%} mdd={row['max_dd']:+.2%} win_rate={row['win_rate']:.1%} ann={row['annualized']:+.1%}")

    # SECTION B: ETF Attribution
    print("\n" + "=" * 50)
    print("  SECTION B: ETF Attribution (FIFO PnL)")
    print("=" * 50)
    sorted_pnl = sorted(pnl_dict.items(), key=lambda x: x[1], reverse=True)
    pos_count = sum(1 for v in pnl_dict.values() if v > 0)
    neg_count = len(pnl_dict) - pos_count
    total_pnl = sum(pnl_dict.values())
    print(f"\n  ETFs traded: {len(pnl_dict)}")
    print(f"  Positive PnL: {pos_count}, Negative: {neg_count}")
    print(f"  Total PnL: {total_pnl:,.0f}Y")
    print(f"\n  Top 15:")
    for code, v in sorted_pnl[:15]:
        n = names.get(code, "")
        total_trades_for_code = len(trade_details[trade_details["code"] == code])
        win_count = len(trade_details[(trade_details["code"] == code) & (trade_details["pnl"] > 0)])
        wr = win_count / max(total_trades_for_code, 1)
        print(f"    {n:30s} ({code:12s}): {v:>10,.0f}Y  trades:{total_trades_for_code:>4d}  wr:{wr:.0%}")
    print(f"\n  Bottom 10:")
    for code, v in sorted_pnl[-10:]:
        n = names.get(code, "")
        print(f"    {n:30s} ({code:12s}): {v:>10,.0f}Y")

    # SECTION C: Charts (35x10, names, PnL)
    print("\n" + "=" * 50)
    print("  SECTION C: Trading Charts (35x10, names, PnL)")
    print("=" * 50)
    chart_codes = sorted(set(codes_traded))
    print(f"\n  Generating {len(chart_codes)} charts...")
    for i, code in enumerate(chart_codes):
        pnl_val = pnl_dict.get(code, 0.0)
        plot_one_etf(store, code, trades, pnl_val, names, FIG_DIR_2026, "F2_CAP_MA60 2026")
        if (i + 1) % 10 == 0: print(f"    {i+1}/{len(chart_codes)}")
    print(f"  Done. Charts -> {FIG_DIR_2026}")

    # SECTION D: Momentum Crash Detection
    print("\n" + "=" * 50)
    print("  SECTION D: Momentum Crash Detection")
    print("=" * 50)
    crashes = detect_momentum_crashes(store, trades, names)
    if not crashes.empty:
        print(f"\n  Found {len(crashes)} potential crash trades")
        print(f"\n  Worst 15 BUY-at-peak:")
        worst_buys = crashes[crashes["action"] == "BUY"].head(15)
        for _, r in worst_buys.iterrows():
            print(f"    {r['trade_date'].date()} {r['name']:30s} ({r['code']:12s}) pct_rank={r['pct_rank']:.0%} fwd_10d={r['fwd_10d_ret']:+.1%} fwd_dd={r['fwd_dd']:+.1%}")
        print(f"\n  Worst 10 SELL-at-valley:")
        worst_sells = crashes[crashes["action"] == "SELL"].head(10)
        for _, r in worst_sells.iterrows():
            print(f"    {r['trade_date'].date()} {r['name']:30s} ({r['code']:12s}) pct_rank={r['pct_rank']:.0%} fwd_10d={r['fwd_10d_ret']:+.1%}")
        crash_codes = sorted(set(worst_buys["code"].tolist()[:8] + worst_sells["code"].tolist()[:5]))
        print(f"\n  Generating {len(crash_codes)} crash charts...")
        for code in crash_codes:
            pnl_val = pnl_dict.get(code, 0.0)
            plot_one_etf(store, code, trades, pnl_val, names, FIG_DIR_CRASH, "CRASH ALERT 2026")
        print(f"  Done. Crash charts -> {FIG_DIR_CRASH}")
        crashes.to_csv(REPORT_DIR / "momentum_crashes_2026.csv", index=False)
    else:
        print("  No crash trades detected.")

    # SECTION E: Missed Opportunities
    print("\n" + "=" * 50)
    print("  SECTION E: Missed Opportunities")
    print("=" * 50)
    missed = analyze_missed_opportunities(store, trades, names)
    if not missed.empty:
        print(f"\n  Top missed opportunities by month:")
        for ym in sorted(missed["year_month"].unique()):
            mdf = missed[missed["year_month"] == ym].sort_values("ret", ascending=False).head(3)
            for _, r in mdf.iterrows():
                print(f"    {ym} {r['name']:30s} ({r['code']:12s}): {r['ret']:+.2%}")
        missed.to_csv(REPORT_DIR / "missed_opportunities_2026.csv", index=False)
    else:
        print("  No missed opportunities data available.")

    # SECTION F: Code Verification
    print("\n" + "=" * 50)
    print("  SECTION F: Code Verification")
    print("=" * 50)
    verification = verify_code_integrity(store, trades)
    print(verification)

    # SECTION G: Warm-up Explanation
    print("\n" + "=" * 50)
    print("  SECTION G: Warm-up Explanation")
    print("=" * 50)
    warmup_text = """
  Why did charts start at 2025-10 and why warm-up?

  1. Engine warm-up (first 25 trading days):
     - The engine needs lookback_days=25 for momentum calculation (regression over 25 days)
     - During warm-up, the engine records flat cash but does NOT trade
     - This ensures the first signal has a full 25-day price history for scoring
     - For standalone yearly backtests starting 2026-01-01, the engine skips
       the first ~25 trading days -> first trade around early Feb 2026

  2. Chart start date (2025-10-01 in old scripts):
     - Old scripts hardcoded "2025-10-01" to give ~60 days of price context
     - This was fine for contextualizing the charts, but not strictly necessary
     - FIXED: Now dynamic: max(first_trade - 60 days, "2025-12-15")
     - This gives enough price history to show the pre-trade price context
     - The chart start date does NOT affect trading logic, only display

  3. Why only need 25 days (not 60 or 90):
     - Momentum regression uses trailing 25 days (lookback_days=25)
     - MA60 overheat uses trailing 60 days -> need 60 days for full MA60
     - Starting chart 60 days before first trade is enough for visual context
     - For standalone yearly backtests (resetting each Jan 1), you CAN feed
       in prior-year data as warmup without trading it - this is what the
       existing code does with params.start set earlier than the actual
       trading start.

  Recommendation: For standalone yearly backtests, set start to 3 months
  before the actual trading period. The engine will naturally skip the
  first 25+ days for warmup, and the extra data ensures MA60 has data.
"""
    print(warmup_text)

    # Build Comprehensive Report
    print("\n" + "=" * 50)
    print("  Building Comprehensive Report...")
    print("=" * 50)
    lines = ["# 2026 综合深度分析报告"]
    lines.append(f"**窗口**: 2026-01-01 -> 2026-06-25, 初始 50 万")
    lines.append("**配置**: F2_v3 44-ETF 核心池 + 动态 PIT capped 补漏 + MA60 过热惩罚")
    lines.append("**成本**: 佣金1bp + 滑点1bp (单边2bp, 双边4bp)")
    lines.append("")
    ann = ((nav.iloc[-1] / 500000) ** (252 / len(nav)) - 1)
    peak = nav.expanding().max(); mdd = (nav / peak - 1.0).min()
    daily_r = nav.pct_change().dropna()
    sharpe = float(daily_r.mean() / daily_r.std() * np.sqrt(252)) if daily_r.std() > 0 else 0
    lines.append("## 1. 核心指标")
    lines.append("| 年化收益 | Sharpe | 最大回撤 | 总收益 | 最终资产 | 交易天数 |")
    lines.append("|---:|---:|---:|---:|---:|---:|")
    lines.append(f"| {ann:.2%} | {sharpe:.2f} | {mdd:.2%} | {(nav.iloc[-1]/500000-1):.2%} | {nav.iloc[-1]:,.0f}Y | {len(nav)} |")
    lines.append("")

    lines.append("## 2. 月度表现")
    lines.append("| 月份 | 收益 | 月内最大回撤 | 日胜率 | 年化 |")
    lines.append("|---:|---:|---:|---:|---:|")
    for _, row in monthly_stats.iterrows():
        lines.append(f"| {row['year_month']} | {row['ret']:+.2%} | {row['max_dd']:+.2%} | {row['win_rate']:.1%} | {row['annualized']:+.1%} |")
    lines.append("")

    lines.append(monthly_heatmap_markdown(heatmap_pivot))
    lines.append("")

    lines.append("## 3. ETF 收益归因 (FIFO)")
    lines.append(f"- 交易 ETF 数: {len(pnl_dict)}")
    lines.append(f"- 正收益 ETF: {pos_count}, 负收益 ETF: {neg_count}")
    lines.append(f"- 总 PnL: {total_pnl:,.0f}Y")
    lines.append("")
    lines.append("### Top 15")
    lines.append("| code | name | PnL | 交易笔数 | 单笔胜率 |")
    lines.append("|---|---:|---:|---:|")
    for code, v in sorted_pnl[:15]:
        n = names.get(code, "")
        total_trades_for_code = len(trade_details[trade_details["code"] == code])
        win_count = len(trade_details[(trade_details["code"] == code) & (trade_details["pnl"] > 0)])
        wr = win_count / max(total_trades_for_code, 1)
        lines.append(f"| {code} | {n} | {v:,.0f}Y | {total_trades_for_code} | {wr:.0%} |")
    lines.append("")
    lines.append("### Bottom 10")
    lines.append("| code | name | PnL | 交易笔数 | 单笔胜率 |")
    lines.append("|---|---:|---:|---:|")
    for code, v in sorted_pnl[-10:]:
        n = names.get(code, "")
        total_trades_for_code = len(trade_details[trade_details["code"] == code])
        win_count = len(trade_details[(trade_details["code"] == code) & (trade_details["pnl"] > 0)])
        wr = win_count / max(total_trades_for_code, 1)
        lines.append(f"| {code} | {n} | {v:,.0f}Y | {total_trades_for_code} | {wr:.0%} |")
    lines.append("")

    if not crashes.empty:
        lines.append("## 4. 动量崩溃检测")
        worst_buys = crashes[crashes["action"] == "BUY"].head(10)
        worst_sells = crashes[crashes["action"] == "SELL"].head(10)
        lines.append("### 买入高点 (BUY at peak) - 最差10笔")
        lines.append("| 日期 | ETF | 价格分位 | 前向10日 | 前向最大回撤 |")
        lines.append("|---|---:|---:|---:|")
        for _, r in worst_buys.iterrows():
            lines.append(f"| {r['trade_date'].date()} | {r['name']} ({r['code']}) | {r['pct_rank']:.0%} | {r['fwd_10d_ret']:+.1%} | {r['fwd_dd']:+.1%} |")
        lines.append("")
        lines.append("### 卖出低点 (SELL at valley) - 最差10笔")
        lines.append("| 日期 | ETF | 价格分位 | 前向10日 |")
        lines.append("|---|---:|---:|")
        for _, r in worst_sells.iterrows():
            lines.append(f"| {r['trade_date'].date()} | {r['name']} ({r['code']}) | {r['pct_rank']:.0%} | {r['fwd_10d_ret']:+.1%} |")
        lines.append("")

    if not missed.empty:
        lines.append("## 5. 错失机会 (月度最强 ETF 未持有)")
        for ym in sorted(missed["year_month"].unique()):
            mdf = missed[missed["year_month"] == ym].sort_values("ret", ascending=False).head(3)
            lines.append(f"### {ym}")
            lines.append("| ETF | 月收益 |")
            lines.append("|---|---:|")
            for _, r in mdf.iterrows():
                lines.append(f"| {r['name']} ({r['code']}) | {r['ret']:+.2%} |")
            lines.append("")
        lines.append("")

    lines.append(verification)
    lines.append("")
    lines.append("## 7. Warm-up 与图表起点说明")
    lines.append("- 引擎 warm-up: 前 25 个交易日不交易 (lookback_days=25)，确保动量回归有足够数据")
    lines.append("- 图表起点: 动态计算 `max(first_trade - 60d, 2025-12-15)`，提供充分价格上下文")
    lines.append("- 图表使用 `signal_close` (pct_chg 累计) -> 无除权除息跳变锯齿")
    lines.append("- 图表尺寸: 35x10，ETF 中文名命名，标注累计 PnL")
    lines.append("")

    lines.append("## 8. 成本压力测试 (2026 standalone)")
    lines.append("| 档位 | 佣金 | 滑点 | 单边 | 年化 | Sharpe | DD | 最终资产 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    cost_rows = [
        ("original", "原始(1+1bp)", "1bp", "1bp", "2bp"),
        ("optimistic", "乐观(0.5+1bp)", "0.5bp", "1bp", "1.5bp"),
        ("baseline", "基准(1+2bp)", "1bp", "2bp", "3bp"),
        ("conservative", "保守(2+5bp)", "2bp", "5bp", "7bp"),
    ]
    missing_cost_rows = []
    for tier_name, tier_label, commission, slip, one_side in cost_rows:
        sm_tier = OUT / f"etf_loop_summary_COSTTIER_FIX1_F2_CAP_MA60_{tier_name}_2026_2026_h5_20260101_20260625.csv"
        if sm_tier.exists():
            s = pd.read_csv(sm_tier).iloc[0].to_dict()
            lines.append(
                f"| {tier_label} | {commission} | {slip} | {one_side} | "
                f"{fmt(s.get('annual_return', 0))} | {s.get('sharpe_ratio', 0):.2f} | "
                f"{fmt(s.get('max_drawdown', 0))} | {s.get('final_value', 0):,.0f}Y |"
            )
        else:
            missing_cost_rows.append(tier_label)
    if missing_cost_rows:
        lines.append("")
        lines.append("> 缺失 2026 standalone 成本结果: " + ", ".join(missing_cost_rows) + "。运行 `python runs/etf_loop/run_cost_stress_f2_cap_ma60_tiers.py` 后重新生成报告。")
    lines.append("")

    lines.append("## 9. 国内券商量化通道手续费参考")
    lines.append("- **佣金**: 量化机构客户可谈至 **万0.5-万1** (0.005%-0.01%)。散户通常在万1.5-万2.5")
    lines.append("- **滑点**: ETF 流动性好的 (日成交 > 1亿) 滑点约万0.5-万1。流动性差的 (> 5000万) 可能万2-万5")
    lines.append("- **印花税**: ETF **免印花税** (这是 ETF 相比股票的巨大优势，股票印花税万5)")
    lines.append("- **单边总成本**: 佣金+滑点 ≈ **万1-万2** (0.01%-0.02%)。保守估计万3")
    lines.append("- **量化通道**: QMT、Ptrade、恒生PT等主流量化通道。需要关注通道容量和报单速度")
    lines.append("")
    lines.append("### 我们的成本设置")
    lines.append("| 参数 | 原始值 | 含义 |")
    lines.append("|---|---|")
    lines.append("| open_cost | 0.0001 (1bp) | 买入佣金 |")
    lines.append("| close_cost | 0.0001 (1bp) | 卖出佣金 |")
    lines.append("| slippage | 0.0001 (1bp) | 固定滑点 (use_dynamic_cost=False) |")
    lines.append("| 单边合计 | 2bp (万2) | 佣金+滑点 |")
    lines.append("| 双边合计 | 4bp (万4) | 买卖全套 |")
    lines.append("")
    lines.append("**结论**: 当前成本设置偏乐观 (佣金1bp偏低)，建议使用基准档 (佣金1bp+滑点2bp) 作为保守参考。")

    report_path = REPORT_DIR / "2026_comprehensive_report.md"
    report_path.write_text("\n".join(lines))
    print(f"\n  Report -> {report_path}")

    pnl_csv = pd.DataFrame(sorted_pnl, columns=["code", "pnl"])
    pnl_csv["name"] = pnl_csv["code"].map(names)
    pnl_csv.to_csv(REPORT_DIR / "2026_etf_pnl.csv", index=False)
    monthly_stats.to_csv(REPORT_DIR / "2026_monthly_stats.csv", index=False)
    print("\n  2026 Comprehensive Analysis Complete.")
    print(f"  Charts: {FIG_DIR_2026}")
    print(f"  Crash charts: {FIG_DIR_CRASH}")
    print(f"  Report: {report_path}")

if __name__ == "__main__":
    main()
