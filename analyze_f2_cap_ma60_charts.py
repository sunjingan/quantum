#!/usr/bin/env python3
"""
F2_CAP_MA60 — All ETF trade charts. 35×10, named by ETF name, per-ETF PnL included.
Uses signal_close (pct_chg continuous adjusted) to avoid raw-close dividend/split jumps.
"""
from __future__ import annotations

import os, sys, re
from datetime import timedelta
from pathlib import Path

import numpy as np, pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from strategies.etf_loop_strategy import ETFDailyStore, SectorProsperityCache

os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".matplotlib_cache"))
import matplotlib; matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

OUT = BASE_DIR / "outputs" / "etf_loop"
CACHE = Path("data/tushare_cache/sector_prosperity")
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"
FIG_DIR = REPORT_DIR / "trade_charts"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

TAG_MAIN = "ADJCORE_F2_CAP_MA60_OPEN_D1"

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


def fmt_cny(x: float) -> str:
    if abs(x) >= 1e6: return f"{x/1e6:.2f}M"
    if abs(x) >= 1e4: return f"{x/1e4:.1f}万"
    return f"{x:,.0f}"


def load_names() -> dict[str, str]:
    path = CACHE / "fund_basic_etf.csv"
    if not path.exists(): return {}
    df = pd.read_csv(path, dtype={"ts_code": str})
    if "name" not in df.columns: return {}
    return dict(zip(df["ts_code"].astype(str), df["name"].astype(str), strict=False))


def load_main() -> tuple[pd.DataFrame, dict]:
    t_path = sorted(OUT.glob(f"etf_loop_targets_{TAG_MAIN}_h*_20130701_20260625.csv"))
    s_path = sorted(OUT.glob(f"etf_loop_summary_{TAG_MAIN}_h*_20130701_20260625.csv"))
    if not t_path or not s_path:
        raise FileNotFoundError("Main F2_CAP_MA60 data missing")
    trades = pd.read_csv(t_path[0], dtype={"ts_code": str})
    summary = pd.read_csv(s_path[0]).iloc[0].to_dict()
    return trades, summary


def build_store_for_codes(codes: list[str]) -> ETFDailyStore:
    codes_all = sorted(set(codes) | {"sh000300"})
    cache = SectorProsperityCache(TOKEN_PATH, CACHE_DIR)
    return ETFDailyStore(cache, codes_all, "2013-07-01", "2026-06-26")


def compute_per_etf_pnl(trades: pd.DataFrame) -> dict[str, float]:
    """FIFO PnL per ETF"""
    trades = trades.copy()
    trades["trade_date"] = pd.to_datetime(trades["trade_date"])
    trades["net_cost"] = pd.to_numeric(trades.get("net_cost", 0), errors="coerce").fillna(0)
    trades["net_proceeds"] = pd.to_numeric(trades.get("net_proceeds", 0), errors="coerce").fillna(0)
    trades["shares"] = pd.to_numeric(trades.get("shares", 0), errors="coerce").fillna(0).astype(float)
    trades["action"] = trades["action"].astype(str)

    pnl: dict[str, float] = {}
    lots: dict[str, list[tuple[float, float]]] = {}

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
                batch_pnl = (proceeds / shares) * take - lot[1] * take
                pnl[code] = pnl.get(code, 0.0) + batch_pnl
                lot[0] -= take
                remaining -= take
                if lot[0] <= 0: lots[code].pop(0)
    return pnl


def safe_filename(name: str, code: str) -> str:
    short = code.replace(".", "")[-6:]
    name = re.sub(r'[\\/*?:"<>|]', '', name).strip()
    if len(name) > 40: name = name[:40]
    return f"{name}_{short}"


def plot_one(store, code, trades, per_etf_pnl, summary, names) -> Path | None:
    code_trades = trades[trades["ts_code"].astype(str) == code]
    if code_trades.empty or code not in store.signal_close.columns:
        return None

    first_trade = pd.to_datetime(code_trades["trade_date"]).min()
    start_plot = first_trade - timedelta(days=120)
    end_plot = pd.Timestamp("2026-06-25")

    # CRITICAL: use signal_close (pct_chg adjusted), NOT raw close
    # raw close has dividend/split jumps causing jagged sawtooth patterns
    raw = store.signal_close[code].loc[start_plot:end_plot].dropna()
    if len(raw) < 5: return None

    # forward-fill for cross-market holiday gaps
    close_ffill = raw.ffill()
    nav = close_ffill / close_ffill.iloc[0]

    buys = code_trades[code_trades["action"].astype(str).eq("BUY")]
    sells = code_trades[code_trades["action"].astype(str).eq("SELL")]
    bd = nav.reindex(pd.to_datetime(buys["trade_date"].dropna())).dropna()
    sd = nav.reindex(pd.to_datetime(sells["trade_date"].dropna())).dropna()

    fig, ax = plt.subplots(figsize=(35, 10))
    ax.plot(nav.index, nav.values, color="#222222", linewidth=1.0, label="signal close (pct_chg adjusted, ffill)")
    if len(bd): ax.scatter(bd.index, bd.values, s=18, color="#d62728", edgecolor="white",
                           linewidth=0.3, label="BUY", zorder=3)
    if len(sd): ax.scatter(sd.index, sd.values, s=18, color="#1f77b4", edgecolor="white",
                           linewidth=0.3, label="SELL", zorder=3)

    name = names.get(code, "")
    etf_pnl = per_etf_pnl.get(code, 0.0)
    sign = "+" if etf_pnl >= 0 else ""
    title = (
        f"F2_CAP_MA60 | {name}({code}) | PnL: {sign}¥{fmt_cny(etf_pnl)} | "
        f"buys {len(buys)} sells {len(sells)}"
    )
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("signal close (1.0=first date)")
    ax.grid(True, alpha=0.15)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fname = safe_filename(name, code) + ".png"
    path = FIG_DIR / fname
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main():
    setup_fonts()
    names = load_names()
    print("=== F2_CAP_MA60 Charts (signal_close, 35×10, named) ===")

    trades, summary = load_main()
    codes_traded = sorted(trades["ts_code"].dropna().astype(str).unique())
    print(f"Building store for {len(codes_traded)} codes...")
    store = build_store_for_codes(codes_traded)
    print(f"Store: {len(store.signal_close.columns)} codes with signal_close")

    per_etf_pnl = compute_per_etf_pnl(trades)
    pos_count = sum(1 for v in per_etf_pnl.values() if v > 0)
    neg_count = sum(1 for v in per_etf_pnl.values() if v < 0)
    print(f"Per-ETF PnL: {pos_count} positive, {neg_count} negative")

    print("Generating charts...")
    saved = 0
    for i, code in enumerate(codes_traded):
        p = plot_one(store, code, trades, per_etf_pnl, summary, names)
        if p is not None: saved += 1
        if (i + 1) % 10 == 0: print(f"  charted {i + 1}/{len(codes_traded)}")
    print(f"Saved {saved} charts → {FIG_DIR}")
    print("Done.")

if __name__ == "__main__":
    main()
