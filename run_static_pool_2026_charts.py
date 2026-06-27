#!/usr/bin/env python3
"""2026 standalone: ORIG38 static & F2 static, holdings=1 & 5. No warmup. Charts."""
from __future__ import annotations
import sys, re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import numpy as np, pandas as pd
from strategies.etf_loop_strategy import ETFDailyStore, SectorProsperityCache, _jq_to_ts, FULL_ETF_POOL_JQ
from strategies.etf_loop_engine import EngineParams, run_and_save
from run_multi_setting_pressure_tests import load_f2_pool

os = __import__('os')
os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".matplotlib_cache"))
import matplotlib; matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

OUT = BASE_DIR / "outputs" / "etf_loop"
CACHE = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity"
TOKEN = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"
CHART_DIR = REPORT_DIR / "trade_charts_2026_static_v2"
CHART_DIR.mkdir(parents=True, exist_ok=True)

START, TSTART, END = "2025-10-01", "2026-01-02", "2026-06-25"

def setup_fonts():
    for p in ["/System/Library/Fonts/Hiragino Sans GB.ttc","/System/Library/Fonts/STHeiti Medium.ttc","/Library/Fonts/Arial Unicode.ttf"]:
        if Path(p).exists(): fm.fontManager.addfont(p); prop = fm.FontProperties(fname=p); plt.rcParams["font.family"] = prop.get_name(); break
    plt.rcParams["axes.unicode_minus"] = False

def load_names():
    path = CACHE / "fund_basic_etf.csv"
    if not path.exists(): return {}
    df = pd.read_csv(path, dtype={"ts_code": str})
    return dict(zip(df["ts_code"].astype(str), df["name"].astype(str), strict=False))

def safe_fname(name, code):
    short = code.replace(".", "")[-6:]
    name = re.sub(r'[\\/*?:"<>|]', '', name).strip()
    if not name: name = code.replace(".", "")
    if len(name) > 40: name = name[:40]
    return f"{name}_{short}"

def compute_fifo_pnl(trades):
    trades = trades.copy(); trades["trade_date"] = pd.to_datetime(trades["trade_date"])
    for c in ["net_cost", "net_proceeds"]: trades[c] = pd.to_numeric(trades.get(c, 0), errors="coerce").fillna(0)
    trades["shares"] = pd.to_numeric(trades.get("shares", 0), errors="coerce").fillna(0).astype(float)
    trades["action"] = trades["action"].astype(str)
    pnl = {}; lots = {}
    for _, r in trades.sort_values(["trade_date", "date"]).iterrows():
        code = str(r["ts_code"]); shares = float(r["shares"]); act = r["action"]
        if shares <= 0: continue
        if act == "BUY": cpp = float(r["net_cost"]) / shares; lots.setdefault(code, []).append([shares, cpp])
        elif act == "SELL":
            proceeds = float(r["net_proceeds"]); remaining = shares
            while remaining > 0 and lots.get(code):
                lot = lots[code][0]; take = min(remaining, lot[0])
                pnl[code] = pnl.get(code, 0.0) + (proceeds / shares) * take - lot[1] * take
                lot[0] -= take; remaining -= take
                if lot[0] <= 0: lots[code].pop(0)
    return pnl

def run_one(tag, pool_ts, holdings):
    """Run one config, return (equity, trades, stats)."""
    p = EngineParams(
        start=START, end=END, exp_tag=tag, etf_pool_ts=pool_ts, holdings_num=holdings,
        lookback_days=25, trading_start=TSTART,
        use_dynamic_pool=False, mr_ma_period=0, mr_penalty=0,
        use_atr_stop_loss=True, atr_multiplier=2.0,
        open_cost=0.0001, close_cost=0.0001, slippage=0.0001,
        execution_price_mode="open", execution_delay_days=1,
    )
    sm = OUT / f"etf_loop_summary_{tag}_h{holdings}_{START.replace('-','')}_{END.replace('-','')}.csv"
    if sm.exists():
        eq = pd.read_csv(OUT / f"etf_loop_equity_{tag}_h{holdings}_{START.replace('-','')}_{END.replace('-','')}.csv", parse_dates=["date"])
        trades = pd.read_csv(OUT / f"etf_loop_targets_{tag}_h{holdings}_{START.replace('-','')}_{END.replace('-','')}.csv", dtype={"ts_code": str})
        stats = pd.read_csv(sm).iloc[0].to_dict()
    else:
        eq, trades, audit = run_and_save(p, OUT); stats = audit["stats"]
    if "date" in eq.columns: eq = eq.set_index("date")
    eq = eq.sort_index()
    return eq, trades, stats

# ── Pools ──
f2p = load_f2_pool()
orig38p = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)

configs = [
    ("ORIG38_5ETF", orig38p, 5),
    ("ORIG38_1ETF", orig38p, 1),
    ("F2_STATIC_5ETF", f2p, 5),
    ("F2_STATIC_1ETF", f2p, 1),
]

setup_fonts()
names = load_names()
results = {}

print("=" * 80)
print("  2026 Static Pool Standalone (no warmup, trading_start=2026-01-02)")
print("=" * 80)

for tag, pool, h in configs:
    full_tag = f"STATIC2026_{tag}"
    print(f"\n→ {full_tag}  holdings={h}")
    eq, trades, stats = run_one(full_tag, pool, h)
    nav = eq["portfolio_value"].loc["2026-01-01":]
    pnl = compute_fifo_pnl(trades)
    results[tag] = {"eq": eq, "trades": trades, "stats": stats, "pnl": pnl, "nav": nav}
    
    ann = ((nav.iloc[-1]/500000)**(252/len(nav))-1) if len(nav) > 0 else 0
    mdd = (nav/nav.expanding().max()-1).min() if len(nav) > 0 else 0
    print(f"  Ann: {ann*100:.2f}%, DD: {mdd*100:.2f}%, Final: {nav.iloc[-1]:,.0f}, Trades: {len(trades)}")
    pos = sum(1 for v in pnl.values() if v > 0)
    print(f"  ETFs: {len(pnl)}, Positive: {pos}/{len(pnl)}, PnL: {sum(pnl.values()):,.0f}")

# ── Charts for all ──
print(f"\n{'='*80}")
print(f"  Generating charts (35×10, names, PnL) → {CHART_DIR}")
print(f"{'='*80}")

all_codes = set()
for tag in results:
    all_codes |= set(results[tag]["trades"]["ts_code"].dropna().astype(str).unique())
cache = SectorProsperityCache(TOKEN, CACHE_DIR)
store = ETFDailyStore(cache, sorted(all_codes), "2025-10-01", "2026-06-27")
print(f"  Store: {len(store.signal_close.columns)} codes")

total_charts = 0
for tag, _, _ in configs:
    res = results[tag]
    trades = res["trades"]; pnl = res["pnl"]
    codes = sorted(trades["ts_code"].dropna().astype(str).unique())
    print(f"\n  {tag} ({len(codes)} ETFs):")
    
    for i, code in enumerate(codes):
        if code not in store.signal_close.columns: continue
        ct = trades[trades["ts_code"].astype(str) == code]
        if ct.empty: continue
        ct_dates = pd.to_datetime(ct["trade_date"]).dropna()
        if ct_dates.empty: continue
        first_trade = ct_dates.min()
        plot_start = max(first_trade - pd.Timedelta(60, unit="D"), pd.Timestamp("2025-12-15"))
        close_raw = store.signal_close[code].loc[plot_start:"2026-06-27"].dropna().ffill()
        if len(close_raw) < 5: continue
        nav_curve = close_raw / close_raw.iloc[0]
        
        buys = ct[ct["action"].astype(str).eq("BUY")]
        sells = ct[ct["action"].astype(str).eq("SELL")]
        bd = nav_curve.reindex(pd.to_datetime(buys["trade_date"].dropna())).dropna()
        sd = nav_curve.reindex(pd.to_datetime(sells["trade_date"].dropna())).dropna()
        
        fig, ax = plt.subplots(figsize=(35, 10))
        ax.plot(nav_curve.index, nav_curve.values, color="#222222", linewidth=1.2, label="signal close")
        if len(bd): ax.scatter(bd.index, bd.values, s=60, color="#d62728", edgecolor="white", linewidth=0.5, label="BUY", zorder=3, alpha=0.85)
        if len(sd): ax.scatter(sd.index, sd.values, s=60, color="#1f77b4", edgecolor="white", linewidth=0.5, label="SELL", zorder=3, alpha=0.85)
        
        name = names.get(code, ""); ep = pnl.get(code, 0.0)
        ax.set_title(f"{tag} | {name} ({code}) | PnL: {ep:,.0f}¥ | buys:{len(buys)} sells:{len(sells)}", fontsize=14, fontweight="bold")
        ax.set_ylabel("revalued (1.0=chart start)", fontsize=10); ax.grid(True, alpha=0.15); ax.legend(loc="upper left", fontsize=10)
        fig.tight_layout()
        fpath = CHART_DIR / f"{tag}_{safe_fname(name, code)}.png"
        fig.savefig(fpath, dpi=150); plt.close(fig)
        total_charts += 1
        if (i+1) % 10 == 0: print(f"    {i+1}/{len(codes)}")

print(f"\n✓ {total_charts} charts saved → {CHART_DIR}")

# ── Summary table ──
print(f"\n{'='*80}")
print(f"  Summary")
print(f"{'='*80}")
print(f"  {'Config':<25s} {'Ann':>8s} {'DD':>8s} {'Final':>12s} {'ETFs':>6s} {'PnL+':>6s} {'TotPnL':>12s}")
print(f"  {'-'*80}")
for tag, _, _ in configs:
    res = results[tag]
    nav = res["nav"]; pnl = res["pnl"]
    ann = ((nav.iloc[-1]/500000)**(252/len(nav))-1) if len(nav) > 0 else 0
    dd = (nav/nav.expanding().max()-1).min() if len(nav) > 0 else 0
    pos = sum(1 for v in pnl.values() if v > 0)
    print(f"  {tag:<25s} {ann*100:7.2f}% {dd*100:7.2f}% {nav.iloc[-1]:>11,.0f} {len(pnl):>6d} {pos:>6d} {sum(pnl.values()):>11,.0f}")

print("\nDone.")
