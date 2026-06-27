#!/usr/bin/env python3
"""2026 F2_CAP_MA60 deep dive — monthly + per-ETF PnL + trading charts"""
from __future__ import annotations
import sys, re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import numpy as np, pandas as pd
from strategies.etf_loop_strategy import ETFDailyStore, SectorProsperityCache

import matplotlib; matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

OUT = BASE_DIR / "outputs" / "etf_loop"
CACHE = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity"
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"
FIG_DIR = REPORT_DIR / "trade_charts_2026"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

def setup_fonts():
    for path in [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]:
        if Path(path).exists():
            fm.fontManager.addfont(path)
            prop = fm.FontProperties(fname=path)
            plt.rcParams["font.family"] = prop.get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False


def load_2026():
    eq = pd.read_csv(OUT / "etf_loop_equity_VAL_YEAR_F2_CAP_MA60_2026_h5_20260101_20260625.csv", parse_dates=["date"])
    trades = pd.read_csv(OUT / "etf_loop_targets_VAL_YEAR_F2_CAP_MA60_2026_h5_20260101_20260625.csv", dtype={"ts_code": str})
    return eq.set_index("date").sort_index(), trades


def load_names():
    path = CACHE / "fund_basic_etf.csv"
    if not path.exists(): return {}
    df = pd.read_csv(path, dtype={"ts_code": str})
    return dict(zip(df["ts_code"].astype(str), df["name"].astype(str), strict=False))


def compute_pnl(trades):
    trades = trades.copy()
    trades["trade_date"] = pd.to_datetime(trades["trade_date"])
    for c in ["net_cost", "net_proceeds"]:
        trades[c] = pd.to_numeric(trades.get(c, 0), errors="coerce").fillna(0)
    trades["shares"] = pd.to_numeric(trades.get("shares", 0), errors="coerce").fillna(0).astype(float)
    trades["action"] = trades["action"].astype(str)
    pnl = {}
    lots = {}
    for _, r in trades.sort_values(["trade_date", "date"]).iterrows():
        code = str(r["ts_code"])
        shares = float(r["shares"])
        act = r["action"]
        if shares <= 0: continue
        if act == "BUY":
            cpp = float(r["net_cost"]) / shares
            lots.setdefault(code, []).append([shares, cpp])
        elif act == "SELL":
            proceeds = float(r["net_proceeds"])
            remaining = shares
            while remaining > 0 and lots.get(code):
                lot = lots[code][0]
                take = min(remaining, lot[0])
                pnl[code] = pnl.get(code, 0.0) + (proceeds / shares) * take - lot[1] * take
                lot[0] -= take
                remaining -= take
                if lot[0] <= 0: lots[code].pop(0)
    return pnl


def safe_fname(name, code):
    short = code.replace(".", "")[-6:]
    name = re.sub(r'[\\/*?:"<>|]', '', name).strip()
    if len(name) > 40: name = name[:40]
    return f"{name}_{short}"


def main():
    setup_fonts()
    names = load_names()
    eq, trades = load_2026()
    nav = eq["portfolio_value"]

    # Monthly
    print("=== 2026 Monthly ===")
    grouped = nav.groupby([nav.index.year, nav.index.month])
    me = grouped.last().sort_index()
    me.index = pd.to_datetime([f"{y}-{m:02d}-01" for y, m in me.index])
    rets = me.pct_change().dropna()
    for idx, r in rets.items():
        print(f"  {idx.strftime('%Y-%m')}: {r*100:+.2f}%")
    print(f"  总: {(nav.iloc[-1]/500000-1)*100:.2f}%, 年化: {((nav.iloc[-1]/500000)**(252/len(nav))-1)*100:.2f}%, DD: {(nav/nav.expanding().max()-1).min()*100:.2f}%")

    # Per-ETF PnL
    pnl = compute_pnl(trades)
    codes_traded = sorted(trades["ts_code"].dropna().astype(str).unique())
    print(f"\n=== ETF PnL ({len(codes_traded)} ETFs traded) ===")
    sorted_pnl = sorted(pnl.items(), key=lambda x: x[1], reverse=True)
    pos = sum(1 for v in pnl.values() if v > 0)
    print(f"  Positive: {pos}, Negative: {len(pnl)-pos}")
    for code, v in sorted_pnl[:10]:
        print(f"  {names.get(code, code)}: ¥{v:,.0f}")
    print(f"  ...")
    for code, v in sorted_pnl[-5:]:
        print(f"  {names.get(code, code)}: ¥{v:,.0f}")

    # Charts for top 15 + bottom 5
    chart_codes = [c for c, _ in sorted_pnl[:15]] + [c for c, _ in sorted_pnl[-5:]]
    chart_codes = sorted(set(chart_codes))

    print(f"\n=== Generating {len(chart_codes)} charts ===")
    # Build small store just for 2026 codes
    store_codes = sorted(set(chart_codes) | set(codes_traded))
    cache = SectorProsperityCache(TOKEN_PATH, CACHE_DIR)
    store = ETFDailyStore(cache, store_codes, "2025-10-01", "2026-06-27")
    print(f"  Store: {len(store.signal_close.columns)} codes")

    for i, code in enumerate(chart_codes):
        if code not in store.signal_close.columns:
            continue
        close_raw = store.signal_close[code].loc["2025-10-01":"2026-06-27"].dropna().ffill()
        if len(close_raw) < 5: continue
        nav_curve = close_raw / close_raw.iloc[0]

        ct = trades[trades["ts_code"].astype(str) == code]
        buys = ct[ct["action"].astype(str).eq("BUY")]
        sells = ct[ct["action"].astype(str).eq("SELL")]
        bd = nav_curve.reindex(pd.to_datetime(buys["trade_date"].dropna())).dropna()
        sd = nav_curve.reindex(pd.to_datetime(sells["trade_date"].dropna())).dropna()

        fig, ax = plt.subplots(figsize=(28, 8))
        ax.plot(nav_curve.index, nav_curve.values, color="#222", linewidth=1.0, label="signal close (ffill)")
        if len(bd): ax.scatter(bd.index, bd.values, s=20, color="#d62728", edgecolor="white", linewidth=0.3, label="BUY", zorder=3)
        if len(sd): ax.scatter(sd.index, sd.values, s=20, color="#1f77b4", edgecolor="white", linewidth=0.3, label="SELL", zorder=3)

        name = names.get(code, "")
        ep = pnl.get(code, 0.0)
        ax.set_title(f"F2_CAP_MA60 2026 | {name}({code}) | PnL: ¥{ep:,.0f} | buys {len(buys)} sells {len(sells)}", fontsize=10)
        ax.set_ylabel("revalued (1.0 = 2025-10-01)")
        ax.grid(True, alpha=0.15)
        ax.legend(loc="upper left", fontsize=8)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"{safe_fname(name, code)}.png", dpi=150)
        plt.close(fig)
        if (i+1) % 5 == 0: print(f"  {i+1}/{len(chart_codes)}")

    print(f"Done. Charts → {FIG_DIR}")

if __name__ == "__main__":
    main()
