#!/usr/bin/env python3
"""2026: F2_STATIC (44 ETFs) vs ORIG38_STATIC (38 ETFs) vs F2_CAP_MA60 comparison"""
from __future__ import annotations
import sys, re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import numpy as np, pandas as pd
from strategies.etf_loop_strategy import ETFDailyStore, SectorProsperityCache, FULL_ETF_POOL_JQ, _jq_to_ts
from strategies.etf_loop_engine import EngineParams, run_and_save
from run_multi_setting_pressure_tests import load_pit_pool, load_f2_pool

import matplotlib; matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

OUT = BASE_DIR / "outputs" / "etf_loop"
CACHE = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity"
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"
FIG_DIR = REPORT_DIR / "trade_charts_2026_static"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

START = "2026-01-01"
END = "2026-06-25"

def setup_fonts():
    for path in ["/System/Library/Fonts/Hiragino Sans GB.ttc","/System/Library/Fonts/STHeiti Medium.ttc","/Library/Fonts/Arial Unicode.ttf"]:
        if Path(path).exists():
            fm.fontManager.addfont(path)
            prop = fm.FontProperties(fname=path)
            plt.rcParams["font.family"] = prop.get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False


def load_names():
    path = CACHE / "fund_basic_etf.csv"
    if not path.exists(): return {}
    df = pd.read_csv(path, dtype={"ts_code": str})
    return dict(zip(df["ts_code"].astype(str), df["name"].astype(str), strict=False))


def pct(x): return "NA" if pd.isna(x) else f"{x*100:.2f}%"


def compute_pnl(trades):
    trades = trades.copy()
    trades["trade_date"] = pd.to_datetime(trades["trade_date"])
    for c in ["net_cost", "net_proceeds"]:
        trades[c] = pd.to_numeric(trades.get(c, 0), errors="coerce").fillna(0)
    trades["shares"] = pd.to_numeric(trades.get("shares", 0), errors="coerce").fillna(0).astype(float)
    trades["action"] = trades["action"].astype(str)
    pnl = {}; lots = {}
    for _, r in trades.sort_values(["trade_date", "date"]).iterrows():
        code = str(r["ts_code"]); shares = float(r["shares"]); act = r["action"]
        if shares <= 0: continue
        if act == "BUY":
            cpp = float(r["net_cost"]) / shares
            lots.setdefault(code, []).append([shares, cpp])
        elif act == "SELL":
            proceeds = float(r["net_proceeds"]); remaining = shares
            while remaining > 0 and lots.get(code):
                lot = lots[code][0]; take = min(remaining, lot[0])
                pnl[code] = pnl.get(code, 0.0) + (proceeds / shares) * take - lot[1] * take
                lot[0] -= take; remaining -= take
                if lot[0] <= 0: lots[code].pop(0)
    return pnl


def run_config(name, tag, extra_params):
    """Run one config, return (equity_df, trades_df, stats_dict)."""
    sm = OUT / f"etf_loop_summary_{tag}_h5_20260101_20260625.csv"
    if sm.exists():
        print(f"  {name}: skip existing")
        eq = pd.read_csv(OUT / f"etf_loop_equity_{tag}_h5_20260101_20260625.csv", parse_dates=["date"])
        trades = pd.read_csv(OUT / f"etf_loop_targets_{tag}_h5_20260101_20260625.csv", dtype={"ts_code": str})
        stats = pd.read_csv(sm).iloc[0].to_dict()
        return eq, trades, stats

    pit = load_pit_pool(); f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2_orig = sorted(set(f2) | set(orig38))

    params = EngineParams(
        start=START, end=END, exp_tag=tag, holdings_num=5, lookback_days=25,
        use_dynamic_pool=False, use_atr_stop_loss=True, atr_multiplier=2.0,
        open_cost=0.0001, close_cost=0.0001, slippage=0.0001,
        execution_price_mode="open", execution_delay_days=1,
        **extra_params
    )
    eq, trades, audit = run_and_save(params, OUT)
    return eq, trades, audit["stats"]


def chart_one(store, code, trades, pnl_dict, tag_label, names):
    if code not in store.signal_close.columns: return None
    first_trade = pd.to_datetime(trades[trades["ts_code"].astype(str) == code]["trade_date"]).min(); plot_start = max(first_trade - pd.Timedelta(days=60), pd.Timestamp("2025-12-15")); close_raw = store.signal_close[code].loc[plot_start:"2026-06-27"].dropna().ffill()
    if len(close_raw) < 5: return None
    nav = close_raw / close_raw.iloc[0]

    ct = trades[trades["ts_code"].astype(str) == code]
    buys = ct[ct["action"].astype(str).eq("BUY")]; sells = ct[ct["action"].astype(str).eq("SELL")]
    bd = nav.reindex(pd.to_datetime(buys["trade_date"].dropna())).dropna()
    sd = nav.reindex(pd.to_datetime(sells["trade_date"].dropna())).dropna()

    fig, ax = plt.subplots(figsize=(28, 8))
    ax.plot(nav.index, nav.values, color="#222", linewidth=1.0)
    if len(bd): ax.scatter(bd.index, bd.values, s=20, color="#d62728", edgecolor="white", linewidth=0.3, zorder=3)
    if len(sd): ax.scatter(sd.index, sd.values, s=20, color="#1f77b4", edgecolor="white", linewidth=0.3, zorder=3)

    name = names.get(code, ""); ep = pnl_dict.get(code, 0.0)
    ax.set_title(f"{tag_label} 2026 | {name}({code}) | PnL: ¥{ep:,.0f} | buys {len(buys)} sells {len(sells)}", fontsize=10)
    ax.set_ylabel("revalued"); ax.grid(True, alpha=0.15); fig.tight_layout()
    fname = re.sub(r'[\\/*?:"<>|]','',name).strip()[:40] + "_" + code.replace(".","")[-6:]
    fig.savefig(FIG_DIR / f"{fname}_{tag_label}.png", dpi=150)
    plt.close(fig)
    return True


def main():
    setup_fonts()
    names = load_names()

    configs = [
        ("F2_STATIC", "STATIC2026_F2",
         {"etf_pool_ts": load_f2_pool(), "mr_ma_period": 0, "mr_penalty": 0, "dynamic_fusion_mode": "union"}),
        ("ORIG38_STATIC", "STATIC2026_ORIG38",
         {"etf_pool_ts": sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ), "mr_ma_period": 0, "mr_penalty": 0, "dynamic_fusion_mode": "union"}),
    ]

    print("=== 2026 Static Pool Comparison ===\n")
    results = {}
    for cname, tag, extra in configs:
        print(f"→ {cname}")
        eq, trades, stats = run_config(cname, tag, extra)
        pnl = compute_pnl(trades)
        results[cname] = {"stats": stats, "pnl": pnl, "trades": trades}
        pos = sum(1 for v in pnl.values() if v > 0)
        print(f"  ann={pct(stats.get('annual_return',0))}, sharpe={stats.get('sharpe_ratio',0):.2f}, dd={pct(stats.get('max_drawdown',0))}")
        print(f"  ETFs traded: {len(pnl)}, positive: {pos}/{len(pnl)}, total PnL: ¥{sum(pnl.values()):,.0f}")
        top3 = sorted(pnl.items(), key=lambda x: x[1], reverse=True)[:3]
        for c, v in top3: print(f"    {names.get(c,c)}: ¥{v:,.0f}")

    # Also load existing F2_CAP_MA60 from earlier run
    cap_trades = pd.read_csv(OUT / "etf_loop_targets_VAL_YEAR_F2_CAP_MA60_2026_h5_20260101_20260625.csv", dtype={"ts_code": str})
    cap_pnl = compute_pnl(cap_trades)
    cap_sm = OUT / "etf_loop_summary_VAL_YEAR_F2_CAP_MA60_2026_h5_20260101_20260625.csv"
    cap_stats = pd.read_csv(cap_sm).iloc[0].to_dict() if cap_sm.exists() else {}
    results["F2_CAP_MA60"] = {"stats": cap_stats, "pnl": cap_pnl, "trades": cap_trades}
    pos = sum(1 for v in cap_pnl.values() if v > 0)
    print(f"\n→ F2_CAP_MA60 (reference)")
    print(f"  ann={pct(cap_stats.get('annual_return',0))}, sharpe={cap_stats.get('sharpe_ratio',0):.2f}, dd={pct(cap_stats.get('max_drawdown',0))}")
    print(f"  ETFs traded: {len(cap_pnl)}, positive: {pos}/{len(cap_pnl)}")

    # ── Charts for all 3 configs ──
    print("\n=== Generating Charts ===")
    all_codes = set()
    for cname in results:
        all_codes |= set(results[cname]["trades"]["ts_code"].dropna().astype(str).unique())
    print(f"  {len(all_codes)} codes across all configs")
    cache = SectorProsperityCache(TOKEN_PATH, CACHE_DIR)
    store = ETFDailyStore(cache, sorted(all_codes), "2025-12-15", "2026-06-27")
    print(f"  Store: {len(store.signal_close.columns)} codes")

    for cname in results:
        print(f"  Charting {cname}...")
        trades = results[cname]["trades"]
        pnl = results[cname]["pnl"]
        codes = sorted(trades["ts_code"].dropna().astype(str).unique())
        saved = 0
        for code in codes:
            if chart_one(store, code, trades, pnl, cname, names):
                saved += 1
        print(f"    {saved}/{len(codes)} charts")

    # ── Report ──
    L = [
        "# 2026 静态池对比: F2 (44 ETFs) vs ORIG38 (38 ETFs) vs F2_CAP_MA60",
        "",
        f"**窗口**: {START} → {END}, 初始 50 万, 佣金1bp + 滑点1bp",
        "",
        "## 1. 核心指标",
        "",
        "| 配置 | 池规模 | 年化 | Sharpe | DD | 交易ETF数 | ETF正PnL | 总PnL |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cname, desc in [("F2_STATIC", "F2_v3 44只"), ("ORIG38_STATIC", "原始 38只"), ("F2_CAP_MA60", "F2_v3 44只 + MA60 + PIT cap")]:
        s = results[cname]["stats"]
        p = results[cname]["pnl"]
        pos = sum(1 for v in p.values() if v > 0)
        L.append(f"| {cname} | {desc} | {pct(s.get('annual_return',0))} | {s.get('sharpe_ratio',0):.2f} | "
                 f"{pct(s.get('max_drawdown',0))} | {len(p)} | {pos}/{len(p)} | ¥{sum(p.values()):,.0f} |")
    L.append("")

    for cname in results:
        L.append(f"## 2. {cname} Top 10 ETF PnL")
        L.append("| code | name | PnL |") ; L.append("|---|---:|")
        for code, v in sorted(results[cname]["pnl"].items(), key=lambda x: x[1], reverse=True)[:10]:
            L.append(f"| {code} | {names.get(code, '')} | ¥{v:,.0f} |")
        L.append("")

    L.append("## 3. 结论")
    L.append(f"- 图表目录: `{FIG_DIR}`")
    L.append("")

    (REPORT_DIR / "static_comparison_2026.md").write_text("\n".join(L))
    print(f"\nReport → {REPORT_DIR / 'static_comparison_2026.md'}")

if __name__ == "__main__":
    main()
