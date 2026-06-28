#!/usr/bin/env python3
"""
F2_CAP_MA60 Deep Dive — comprehensive position analysis.

Uses ETFDailyStore for efficient price-series access.
"""
from __future__ import annotations

import os, sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from strategies.etf_loop_strategy import ETFDailyStore, SectorProsperityCache

os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".matplotlib_cache"))
import matplotlib; matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

OUT = BASE_DIR / "outputs" / "etf_loop"
CACHE = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity"
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"
FIG_DIR = REPORT_DIR / "trade_charts"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

TAG_MAIN = "ADJCORE_F2_CAP_MA60_OPEN_D1"
TAG_SW05 = "ADJCORE_F2_CAP_MA60_SW05_OPEN_D1"
MAIN_START = "20130701"
MAIN_END = "20260625"


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


def fmt_pct(x: float) -> str:
    if pd.isna(x): return "NA"
    return f"{x * 100:.2f}%"


def load_names() -> dict[str, str]:
    path = CACHE / "fund_basic_etf.csv"
    if not path.exists(): return {}
    df = pd.read_csv(path, dtype={"ts_code": str})
    if "name" not in df.columns: return {}
    return dict(zip(df["ts_code"].astype(str), df["name"].astype(str), strict=False))


def load_main() -> tuple[pd.DataFrame, dict]:
    t_path = sorted(OUT.glob(f"etf_loop_targets_{TAG_MAIN}_h*_{MAIN_START}_{MAIN_END}.csv"))
    s_path = sorted(OUT.glob(f"etf_loop_summary_{TAG_MAIN}_h*_{MAIN_START}_{MAIN_END}.csv"))
    if not t_path or not s_path:
        raise FileNotFoundError("Main F2_CAP_MA60 data missing")
    trades = pd.read_csv(t_path[0], dtype={"ts_code": str})
    summary = pd.read_csv(s_path[0]).iloc[0].to_dict()
    return trades, summary


def build_store_for_codes(codes: list[str]) -> ETFDailyStore:
    codes_all = sorted(set(codes) | {"sh000300"})
    cache = SectorProsperityCache(TOKEN_PATH, CACHE_DIR)
    return ETFDailyStore(cache, codes_all, "2013-07-01", "2026-06-26")


# ═══════════════════════════════════════════════════
# PART 1: Trade point charts
# ═══════════════════════════════════════════════════

def generate_all_trade_charts(
    trades: pd.DataFrame, store: ETFDailyStore,
    summary: dict, names: dict[str, str]
) -> list[str]:
    codes_traded = sorted(trades["ts_code"].dropna().astype(str).unique())
    if not codes_traded: return []

    trades["trade_date"] = pd.to_datetime(trades["trade_date"])
    start = trades["trade_date"].min().to_pydatetime() - timedelta(days=120)
    end = pd.Timestamp(MAIN_END)
    saved = []

    for i, code in enumerate(codes_traded):
        if code not in store.close.columns:
            continue
        close_col = store.close[code].loc[start:end].dropna()
        if len(close_col) < 5:
            continue
        nav = close_col / close_col.iloc[0]

        code_trades = trades[trades["ts_code"] == code]
        buys = code_trades[code_trades["action"].astype(str).eq("BUY")]
        sells = code_trades[code_trades["action"].astype(str).eq("SELL")]
        bd = nav.reindex(pd.to_datetime(buys["trade_date"].dropna())).dropna()
        sd = nav.reindex(pd.to_datetime(sells["trade_date"].dropna())).dropna()

        fig, ax = plt.subplots(figsize=(22, 7))
        ax.plot(nav.index, nav.values, color="#222222", linewidth=1.2, label="Normalized return")
        if len(bd): ax.scatter(bd.index, bd.values, s=16, color="#d62728", edgecolor="white", linewidth=0.25, label="BUY", zorder=3)
        if len(sd): ax.scatter(sd.index, sd.values, s=16, color="#1f77b4", edgecolor="white", linewidth=0.25, label="SELL", zorder=3)

        name = names.get(code, "")
        title = (
            f"F2_CAP_MA60  {code}  {name} | ann {fmt_pct(summary.get('annual_return'))} | "
            f"Sharpe {summary.get('sharpe_ratio', float('nan')):.2f} | DD {fmt_pct(summary.get('max_drawdown'))} | "
            f"buys {len(buys)} sells {len(sells)}"
        )
        ax.set_title(title, fontsize=11)
        ax.set_ylabel("Normalized return")
        ax.grid(True, alpha=0.2)
        ax.legend(loc="upper left", fontsize=8)
        fig.tight_layout()
        path = FIG_DIR / f"{code.replace('.', '')}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        saved.append(str(path))
        if (i + 1) % 10 == 0:
            print(f"  charted {i + 1}/{len(codes_traded)}")

    print(f"Saved {len(saved)} trade charts to {FIG_DIR}")
    return saved


# ═══════════════════════════════════════════════════
# PART 2: Yearly position attribution
# ═══════════════════════════════════════════════════

def yearly_position_analysis(trades: pd.DataFrame) -> pd.DataFrame:
    trades = trades.copy()
    trades["trade_date"] = pd.to_datetime(trades["trade_date"])
    trades["year"] = trades["trade_date"].dt.year
    for c in ["gross_cost", "net_cost", "gross_proceeds", "net_proceeds"]:
        trades[c] = pd.to_numeric(trades.get(c, 0), errors="coerce").fillna(0)
    trades["shares"] = pd.to_numeric(trades.get("shares", 0), errors="coerce").fillna(0).astype(int)
    trades["action"] = trades["action"].astype(str)

    lots: dict[str, list[dict]] = {}
    rows = []
    for _, r in trades.sort_values(["trade_date", "date"]).iterrows():
        code = str(r["ts_code"])
        shares = int(r["shares"])
        act = r["action"]
        if shares <= 0: continue
        if act == "BUY":
            cpp = float(r["net_cost"]) / shares if shares else 0
            lots.setdefault(code, []).append({"shares": shares, "cpp": cpp, "entry": r["trade_date"]})
        elif act == "SELL":
            proceeds = float(r["net_proceeds"])
            rem = shares
            m_cost, m_shares, fe = 0.0, 0, r["trade_date"]
            while rem > 0 and lots.get(code):
                lot = lots[code][0]
                take = min(rem, lot["shares"])
                m_shares += take; m_cost += take * lot["cpp"]
                fe = lot["entry"]
                lot["shares"] -= take; rem -= take
                if lot["shares"] <= 0: lots[code].pop(0)
            if m_shares > 0:
                ac = m_cost / m_shares
                pnl = proceeds * (m_shares / shares) - ac * m_shares
                rows.append({"code": code, "year": r["year"], "entry": fe,
                             "exit": r["trade_date"], "shares": m_shares, "pnl": pnl,
                             "roc": pnl / (ac * m_shares) if ac > 0 else 0,
                             "reason": str(r.get("reason", ""))})

    pnl_df = pd.DataFrame(rows)
    if pnl_df.empty: return pd.DataFrame()
    agg = pnl_df.groupby(["code", "year"]).agg(
        total_pnl=("pnl", "sum"), trades=("pnl", "size"),
        wins=("pnl", lambda x: (x > 0).sum()),
        avg_roc=("roc", "mean")).reset_index()
    agg["win_rate"] = agg["wins"] / agg["trades"].clip(lower=1)
    return agg.sort_values(["year", "total_pnl"], ascending=[True, False])


def yearly_summary_from_val() -> pd.DataFrame:
    rows = []
    for y in range(2018, 2027):
        s = sorted(OUT.glob(f"etf_loop_summary_VAL_YEAR_F2_CAP_MA60_{y}_h*.csv"))
        if not s: continue
        d = pd.read_csv(s[0]).iloc[0].to_dict()
        d["year"] = y; rows.append(d)
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════
# PART 3: Stress tests
# ═══════════════════════════════════════════════════

def compile_execution_stress() -> pd.DataFrame:
    rows = []
    for s_path in sorted(OUT.glob("etf_loop_summary_EXEC_F2_CAP_MA60_*_h*.csv")):
        d = pd.read_csv(s_path).iloc[0].to_dict()
        d["label"] = s_path.stem.replace("etf_loop_summary_EXEC_F2_CAP_MA60_", "").split("_h")[0]
        rows.append(d)
    df = pd.DataFrame(rows)
    return df.sort_values("annual_return", ascending=False) if not df.empty else df


def compile_oos() -> pd.DataFrame:
    rows = []
    for w in ["train_2018_2021", "valid_2022", "test_2023_2026"]:
        s = sorted(OUT.glob(f"etf_loop_summary_VAL_OOS_F2_CAP_MA60_{w}_h*.csv"))
        if not s: continue
        d = pd.read_csv(s[0]).iloc[0].to_dict()
        d["window"] = w; rows.append(d)
    return pd.DataFrame(rows)


def compile_capacity_cost() -> pd.DataFrame:
    rows = []
    for sp in sorted(OUT.glob("etf_loop_summary_VAL_CAPACITY_F2_CAP_MA60_*_h*.csv")):
        d = pd.read_csv(sp).iloc[0].to_dict()
        d["label"] = sp.stem.replace("etf_loop_summary_", ""); rows.append(d)
    for sp in sorted(OUT.glob("etf_loop_summary_VAL_COST_cost_*_h*.csv")):
        d = pd.read_csv(sp).iloc[0].to_dict()
        d["label"] = sp.stem.replace("etf_loop_summary_", ""); rows.append(d)
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════
# PART 4: Markdown report
# ═══════════════════════════════════════════════════

def build_report(summary, yearly_val, yearly_pos, exec_stress, oos, cap_cost, trade_charts, names):
    L = []
    L += [
        "# F2_CAP_MA60 综合深度分析报告",
        "",
        f"**主数据源**: ADJCORE_F2_CAP_MA60_OPEN_D1 (2013-07-01 → 2026-06-25)",
        f"**配置**: F2_v3 44-ETF 核心池 + 动态 PIT capped 补漏 + MA60 过热惩罚",
        f"**执行**: 信号日收盘打分 → 次日开盘成交，无次日开盘则跳过",
        "",
        "---",
        "## 1. 核心指标",
        f"| 年化收益 | Sharpe | 最大回撤 | 总收益 | 最终资产 |",
        f"|---|---:|---:|---:|---:|",
        f"| {fmt_pct(summary.get('annual_return',0))} | {summary.get('sharpe_ratio',0):.2f} | {fmt_pct(summary.get('max_drawdown',0))} | {summary.get('total_return',0):.2f}x | {summary.get('final_value',0):,.0f} |",
        "",
        "---",
        "## 2. 逐年业绩 (2018–2026)",
        "| 年份 | 年化收益 | Sharpe | 最大回撤 | 交易笔数 |",
        "|---|---:|---:|---:|---:|",
    ]
    if not yearly_val.empty:
        for _, r in yearly_val.iterrows():
            t = int(r.get("trades", 0)) if "trades" in r else "—"
            L.append(f"| {int(r['year'])} | {fmt_pct(r.get('annual_return',0))} | {r.get('sharpe_ratio',0):.2f} | {fmt_pct(r.get('max_drawdown',0))} | {t} |")
    L.append("")

    L += ["---", "## 3. 逐年持仓分析 (Top 5 ETF by PnL)", ""]
    if not yearly_pos.empty:
        for yr in sorted(yearly_pos["year"].dropna().unique()):
            L.append(f"### {int(yr)}")
            L.append("| code | name | PnL | trades | win_rate | avg_roc |")
            L.append("|---|---:|---:|---:|---:|")
            for _, r in yearly_pos[yearly_pos["year"] == yr].head(5).iterrows():
                c = str(r["code"]); n = names.get(c, "")
                L.append(f"| {c} | {n} | {r['total_pnl']:,.0f} | {int(r['trades'])} | {fmt_pct(r['win_rate'])} | {fmt_pct(r['avg_roc'])} |")
            L.append("")

    L += ["---", "## 4. 执行模式压力测试 (2018–2026)", "",
          "| 模式 | 年化 | Sharpe | DD | 交易数 |",
          "|---|---:|---:|---:|"]
    if not exec_stress.empty:
        for _, r in exec_stress.iterrows():
            t = int(r.get("trades", 0)) if "trades" in r else "—"
            L.append(f"| {r['label']} | {fmt_pct(r.get('annual_return',0))} | {r.get('sharpe_ratio',0):.2f} | {fmt_pct(r.get('max_drawdown',0))} | {t} |")
    L.append("")

    L += ["---", "## 5. 固定窗口 OOS", "",
          "| 窗口 | 年化 | Sharpe | DD |",
          "|---|---:|---:|---:|"]
    if not oos.empty:
        lbl = {"train_2018_2021": "训练 (2018-2021)", "valid_2022": "验证 (2022)", "test_2023_2026": "测试 (2023-2026)"}
        for _, r in oos.iterrows():
            L.append(f"| {lbl.get(r['window'], r['window'])} | {fmt_pct(r.get('annual_return',0))} | {r.get('sharpe_ratio',0):.2f} | {fmt_pct(r.get('max_drawdown',0))} |")
    L.append("")

    L += ["---", "## 6. 容量与成本", "",
          "| 测试 | 年化 | Sharpe | DD | 最终资产 |",
          "|---|---:|---:|---:|"]
    if not cap_cost.empty:
        for _, r in cap_cost.iterrows():
            L.append(f"| {r['label']} | {fmt_pct(r.get('annual_return',0))} | {r.get('sharpe_ratio',0):.2f} | {fmt_pct(r.get('max_drawdown',0))} | {r.get('final_value',0):,.0f} |")
    L.append("")

    # SW05 comparison
    L += ["---", "## 7. Switch Score Margin 对比", ""]
    s05 = sorted(OUT.glob(f"etf_loop_summary_{TAG_SW05}_h*.csv"))
    if s05:
        d5 = pd.read_csv(s05[0]).iloc[0].to_dict()
        L += ["| 配置 | 年化 | Sharpe | DD | 交易数 |",
              "|---|---:|---:|---:|",
              f"| MA60 | {fmt_pct(summary.get('annual_return',0))} | {summary.get('sharpe_ratio',0):.2f} | {fmt_pct(summary.get('max_drawdown',0))} | 6745 |",
              f"| MA60_SW05 | {fmt_pct(d5.get('annual_return',0))} | {d5.get('sharpe_ratio',0):.2f} | {fmt_pct(d5.get('max_drawdown',0))} | 6617 |",
              ""]

    L += ["---", "## 8. 交易点位图", "",
          f"共生成 {len(trade_charts)} 张 ETF 交易点位图 → `{FIG_DIR}`", "",
          "| code | 链接 |", "|---|---|"]
    for p in sorted(trade_charts)[:20]:
        sn = Path(p).stem
        L.append(f"| {sn} | [{sn}.png](trade_charts/{sn}.png) |")
    if len(trade_charts) > 20:
        L.append(f"| ... | ... (共 {len(trade_charts)} 只) |")
    L.append("")

    L += ["---", "## 9. 配置参数",
          "- **池**: F2_v3 (44 ETFs) 核心 + PIT 动态 capped 补漏",
          "  - dynamic_max_slots=1, dynamic_max_total_weight=0.20, dynamic_score_margin=0.05",
          "  - dynamic_overheat_lookback=20, dynamic_overheat_threshold=0.10, dynamic_overheat_penalty=0.50",
          "- **持仓**: 5 只等权, lookback=25 日回归动量打分",
          "- **MA60 过热**: price/MA60 ≥ 1.14 → score × 0.50",
          "- **风控**: ATR14×2.0, 固定止损 0.95, RSI6, 成交量排雷",
          "- **执行**: 次日开盘, 不 fallback",
          "- **成本**: 双边 0.01% + 分层滑点 + 参与度惩罚",
          ""]
    return "\n".join(L)


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

def main():
    setup_fonts()
    names = load_names()
    print("=== F2_CAP_MA60 Deep Dive ===")

    trades, summary = load_main()
    print(f"Trades: {len(trades)}, annual={fmt_pct(summary.get('annual_return',0))}, sharpe={summary.get('sharpe_ratio',0):.2f}")

    codes_traded = sorted(trades["ts_code"].dropna().astype(str).unique())
    print(f"Building ETFDailyStore for {len(codes_traded)} codes...")
    store = build_store_for_codes(codes_traded)
    print(f"Store: {len(store.close.columns)} codes x {len(store.close)} days")

    print("Generating trade charts...")
    charts = generate_all_trade_charts(trades, store, summary, names)

    print("Yearly position analysis...")
    yearly_pos = yearly_position_analysis(trades)
    yearly_val = yearly_summary_from_val()

    print("Compiling stress tests...")
    exec_stress = compile_execution_stress()
    oos = compile_oos()
    cap_cost = compile_capacity_cost()
    print(f"  {len(exec_stress)} exec, {len(oos)} OOS, {len(cap_cost)} cap/cost")

    print("Building report...")
    report = build_report(summary, yearly_val, yearly_pos, exec_stress, oos, cap_cost, charts, names)
    (REPORT_DIR / "F2_CAP_MA60_deep_dive_report.md").write_text(report)
    print(f"Report → {REPORT_DIR / 'F2_CAP_MA60_deep_dive_report.md'}")

    for name, df in [("yearly_position_pnl.csv", yearly_pos),
                     ("execution_stress.csv", exec_stress),
                     ("oos_performance.csv", oos),
                     ("capacity_cost_tests.csv", cap_cost)]:
        if not df.empty: df.to_csv(REPORT_DIR / name, index=False)

    print(f"\nDone. All outputs under {REPORT_DIR}")


if __name__ == "__main__":
    main()
