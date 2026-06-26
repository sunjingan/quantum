#!/usr/bin/env python3
"""Deep-dive diagnostics and visualizations for ETF Loop reruns."""
from __future__ import annotations

import pickle
import sys
from dataclasses import dataclass
from pathlib import Path

import os

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".matplotlib_cache"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from strategies.etf_loop_strategy import ETFDailyStore, FULL_ETF_POOL_JQ, _jq_to_ts
from strategies.sector_prosperity import SectorProsperityCache


OUT = BASE_DIR / "outputs" / "etf_loop"
FIG = OUT / "figures"
START = "2013-07-01"
END = "2026-06-25"
STATIC_TAG = "FINAL13_F2v3_ORIG38"
FUSED_TAG = "FINAL13_F2v3_ORIG38_G2PIT"


@dataclass
class Metrics:
    annual: float
    sharpe: float
    max_dd: float
    win_rate: float
    alpha: float
    beta: float
    total: float
    final_value: float


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def money(x: float) -> str:
    if pd.isna(x):
        return ""
    return f"{x / 10000:.1f}万"


def money_10k_en(x: float) -> str:
    if pd.isna(x):
        return ""
    return f"{x / 10000:.1f}"


def md_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(lines)


def load_name_map() -> dict[str, str]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "fund_basic_etf.csv"
    df = pd.read_csv(path, dtype={"ts_code": str})
    return dict(zip(df["ts_code"].astype(str), df["name"].astype(str)))


def load_f2_orig_pool() -> set[str]:
    f2_path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_F2_v3.csv"
    f2 = set(pd.read_csv(f2_path, dtype={"ts_code": str})["ts_code"].astype(str))
    orig = set(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    return f2 | orig


def load_g2_union() -> set[str]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_G2_PIT_monthly.pkl"
    with open(path, "rb") as f:
        pools = pickle.load(f)
    return set().union(*(set(v) for v in pools.values()))


def paths(tag: str) -> tuple[Path, Path, Path]:
    equity = sorted(OUT.glob(f"etf_loop_equity_{tag}_h*.csv"))
    trades = sorted(OUT.glob(f"etf_loop_targets_{tag}_h*.csv"))
    summary = sorted(OUT.glob(f"etf_loop_summary_{tag}_h*.csv"))
    if not equity or not trades or not summary:
        raise FileNotFoundError(f"Missing output files for tag={tag}")
    return equity[0], trades[0], summary[0]


def load_equity(tag: str) -> pd.DataFrame:
    eq, _, _ = paths(tag)
    return pd.read_csv(eq, parse_dates=["date"]).sort_values("date")


def load_trades(tag: str) -> pd.DataFrame:
    _, tr, _ = paths(tag)
    df = pd.read_csv(tr, parse_dates=["date", "trade_date"])
    for col in ["gross_cost", "net_cost", "gross_proceeds", "net_proceeds", "cost", "score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values(["trade_date", "ts_code", "action"])


def drawdown(values: pd.Series) -> float:
    values = values.dropna()
    return float((values / values.cummax() - 1.0).min()) if len(values) else np.nan


def calc_metrics(eq: pd.DataFrame) -> Metrics:
    eq = eq.sort_values("date").copy()
    ret = eq["portfolio_value"].pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    bench = eq[["date", "benchmark_value"]].dropna().copy()
    bench_ret = bench["benchmark_value"].pct_change().replace([np.inf, -np.inf], np.nan)

    years = max((eq["date"].iloc[-1] - eq["date"].iloc[0]).days / 365.25, 1e-9)
    total = float(eq["portfolio_value"].iloc[-1] / eq["portfolio_value"].iloc[0] - 1.0)
    annual = (1.0 + total) ** (1.0 / years) - 1.0
    sharpe = float(ret.mean() / ret.std() * np.sqrt(252)) if len(ret) > 1 and ret.std() else np.nan
    win_rate = float((ret > 0).mean()) if len(ret) else np.nan

    aligned = pd.concat([ret.rename("strategy"), bench_ret.rename("bench")], axis=1).dropna()
    if len(aligned) > 2 and aligned["bench"].var() > 0:
        beta = float(aligned["strategy"].cov(aligned["bench"]) / aligned["bench"].var())
        alpha = float((aligned["strategy"].mean() - beta * aligned["bench"].mean()) * 252)
    else:
        beta = np.nan
        alpha = np.nan

    return Metrics(
        annual=float(annual),
        sharpe=sharpe,
        max_dd=drawdown(eq["portfolio_value"]),
        win_rate=win_rate,
        alpha=alpha,
        beta=beta,
        total=total,
        final_value=float(eq["portfolio_value"].iloc[-1]),
    )


def rolling_worst_windows(static_eq: pd.DataFrame, fused_eq: pd.DataFrame, window: int = 63, n: int = 6) -> pd.DataFrame:
    df = static_eq[["date", "portfolio_value"]].rename(columns={"portfolio_value": "static"}).merge(
        fused_eq[["date", "portfolio_value"]].rename(columns={"portfolio_value": "fused"}),
        on="date",
        how="inner",
    )
    df["static_ret"] = df["static"] / df["static"].shift(window) - 1.0
    df["fused_ret"] = df["fused"] / df["fused"].shift(window) - 1.0
    df["delta"] = df["fused_ret"] - df["static_ret"]
    candidates = df.dropna().sort_values("delta").reset_index(drop=True)

    selected: list[dict] = []
    used: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for row in candidates.itertuples(index=False):
        end_date = row.date
        start_date = df.loc[df["date"].eq(end_date)].index[0]
        start = df.loc[start_date - window, "date"]
        if any(not (end_date < s or start > e) for s, e in used):
            continue
        used.append((start, end_date))
        selected.append({
            "start": start,
            "end": end_date,
            "static_return": row.static_ret,
            "fused_return": row.fused_ret,
            "excess_return": row.delta,
        })
        if len(selected) >= n:
            break
    return pd.DataFrame(selected)


def build_position_values(trades: pd.DataFrame, dates: pd.Series, store: ETFDailyStore) -> pd.DataFrame:
    dates = pd.DatetimeIndex(pd.to_datetime(dates).sort_values().unique())
    codes = sorted(trades["ts_code"].dropna().astype(str).unique())
    shares = {c: 0 for c in codes}
    grouped = {d: g for d, g in trades.groupby("trade_date")}
    rows: list[dict[str, float]] = []
    for date in dates:
        if date in grouped:
            for r in grouped[date].itertuples(index=False):
                code = str(r.ts_code)
                n = int(getattr(r, "shares", 0) or 0)
                if r.action == "BUY":
                    shares[code] = shares.get(code, 0) + n
                elif r.action == "SELL":
                    shares[code] = shares.get(code, 0) - n
                    if shares[code] <= 0:
                        shares[code] = 0
        row = {"date": date}
        for code, n in shares.items():
            if n <= 0:
                continue
            px = store.latest_price(code, date)
            if not np.isnan(px) and px > 0:
                row[code] = n * px
        rows.append(row)
    return pd.DataFrame(rows).fillna(0.0).set_index("date")


def value_col(df: pd.DataFrame) -> pd.Series:
    buy = df.get("net_cost", pd.Series(index=df.index, dtype=float)).fillna(0.0)
    sell = df.get("net_proceeds", pd.Series(index=df.index, dtype=float)).fillna(0.0)
    return np.where(df["action"].eq("BUY"), buy, sell)


def summarize_window_trades(
    window_id: int,
    start: pd.Timestamp,
    end: pd.Timestamp,
    static_trades: pd.DataFrame,
    fused_trades: pd.DataFrame,
    static_pos: pd.DataFrame,
    fused_pos: pd.DataFrame,
    dynamic_only: set[str],
    name_map: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    def prep(trades: pd.DataFrame, strategy: str) -> pd.DataFrame:
        w = trades[(trades["trade_date"] >= start) & (trades["trade_date"] <= end)].copy()
        if w.empty:
            return pd.DataFrame()
        w["strategy"] = strategy
        w["window_id"] = window_id
        w["name"] = w["ts_code"].map(name_map).fillna("")
        w["is_dynamic_only"] = w["ts_code"].isin(dynamic_only)
        w["trade_value"] = value_col(w)
        return w

    trades = pd.concat([prep(static_trades, "static64"), prep(fused_trades, "fused_dynamic")], ignore_index=True)

    s_avg = static_pos.loc[start:end].mean() if len(static_pos.loc[start:end]) else pd.Series(dtype=float)
    f_avg = fused_pos.loc[start:end].mean() if len(fused_pos.loc[start:end]) else pd.Series(dtype=float)
    exposure = pd.concat([s_avg.rename("static_avg_mv"), f_avg.rename("fused_avg_mv")], axis=1).fillna(0.0)
    exposure["window_id"] = window_id
    exposure["ts_code"] = exposure.index
    exposure["name"] = exposure["ts_code"].map(name_map).fillna("")
    exposure["is_dynamic_only"] = exposure["ts_code"].isin(dynamic_only)
    exposure["avg_mv_delta_fused_minus_static"] = exposure["fused_avg_mv"] - exposure["static_avg_mv"]
    exposure = exposure.reset_index(drop=True)
    return trades, exposure


def make_visuals(metric_rows: pd.DataFrame, windows: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.labelsize": 9,
        "legend.fontsize": 8,
        "figure.dpi": 140,
    })

    final_tags = [
        "FINAL13_ORIG38",
        "FINAL13_F2v3",
        "FINAL13_F2v3_ORIG38",
        "FINAL13_POOL19",
        "FINAL13_G2PIT",
        "FINAL13_ORIG38_G2PIT",
        "FINAL13_F2v3_G2PIT",
        "FINAL13_F2v3_ORIG38_G2PIT",
    ]

    fig, ax = plt.subplots(figsize=(13, 7))
    for tag in final_tags:
        eq = load_equity(tag)
        m = metric_rows.set_index("tag").loc[tag]
        norm = eq["portfolio_value"] / eq["portfolio_value"].iloc[0]
        label = f"{tag} | Ann {pct(m.annual)} | Sharpe {m.sharpe:.2f} | DD {pct(m.max_dd)} | Win {pct(m.win_rate)}"
        ax.plot(eq["date"], norm, linewidth=1.5, label=label)
    ax.set_title("ETF Loop Final 13Y Pool Comparison")
    ax.set_ylabel("Normalized NAV")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left", ncol=1)
    fig.tight_layout()
    fig.savefig(FIG / "etf_loop_final13_equity_metrics.png")
    plt.close(fig)

    core_tags = [t for t in metric_rows["tag"] if not t.startswith("FINAL13")]
    core = metric_rows[metric_rows["tag"].isin(core_tags)].copy()
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
    axes[0].bar(core["tag"], core["annual"] * 100, color="#2f6f73")
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_ylabel("Annual return %")
    axes[0].set_title("Core / J / K Experiments")
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].bar(core["tag"], core["max_dd"] * 100, color="#a14b3f")
    axes[1].set_ylabel("Max drawdown %")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].tick_params(axis="x", rotation=45)
    for idx, r in core.reset_index(drop=True).iterrows():
        axes[0].text(idx, r.annual * 100, f"S {r.sharpe:.2f}\nW {pct(r.win_rate)}", ha="center", va="bottom", fontsize=7)
    fig.tight_layout()
    fig.savefig(FIG / "etf_loop_core_experiment_bars.png")
    plt.close(fig)

    static_eq = load_equity(STATIC_TAG)
    fused_eq = load_equity(FUSED_TAG)
    merged = static_eq[["date", "portfolio_value"]].rename(columns={"portfolio_value": "static"}).merge(
        fused_eq[["date", "portfolio_value"]].rename(columns={"portfolio_value": "fused"}), on="date"
    )
    merged["static_norm"] = merged["static"] / merged["static"].iloc[0]
    merged["fused_norm"] = merged["fused"] / merged["fused"].iloc[0]
    merged["roll63_static"] = merged["static"] / merged["static"].shift(63) - 1.0
    merged["roll63_fused"] = merged["fused"] / merged["fused"].shift(63) - 1.0
    merged["roll63_delta"] = merged["roll63_fused"] - merged["roll63_static"]

    group = pd.read_csv(OUT / "dynamic_pool_group_pnl.csv")
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    axes[0, 0].plot(merged["date"], merged["static_norm"], label=STATIC_TAG, linewidth=1.6)
    axes[0, 0].plot(merged["date"], merged["fused_norm"], label=FUSED_TAG, linewidth=1.6)
    for tag, y in [(STATIC_TAG, 0.98), (FUSED_TAG, 0.88)]:
        m = metric_rows.set_index("tag").loc[tag]
        axes[0, 0].text(
            0.02,
            y,
            f"{tag}: Ann {pct(m.annual)}, Sharpe {m.sharpe:.2f}, Alpha {pct(m.alpha)}, Beta {m.beta:.2f}, Win {pct(m.win_rate)}, DD {pct(m.max_dd)}",
            transform=axes[0, 0].transAxes,
            fontsize=8,
            va="top",
        )
    axes[0, 0].legend()
    axes[0, 0].set_title("Static64 vs Static64 + G2 PIT")
    axes[0, 0].grid(alpha=0.25)

    axes[0, 1].plot(merged["date"], merged["roll63_delta"] * 100, color="#9b3d2e", linewidth=1.1)
    axes[0, 1].axhline(0, color="black", linewidth=0.8)
    axes[0, 1].set_title("Rolling 63D excess return: fused - static")
    axes[0, 1].set_ylabel("pct point")
    axes[0, 1].grid(alpha=0.25)

    labels = ["static codes in fused", "dynamic-only codes"]
    vals = [float(group.loc[group["is_dynamic_only"].eq(False), "pnl"].iloc[0]), float(group.loc[group["is_dynamic_only"].eq(True), "pnl"].iloc[0])]
    axes[1, 0].bar(labels, [v / 10000 for v in vals], color=["#4c78a8", "#f58518"])
    axes[1, 0].set_title("Fused strategy cash-flow PnL by code group")
    axes[1, 0].set_ylabel("PnL, 10k CNY")
    for i, v in enumerate(vals):
        axes[1, 0].text(i, v / 10000, money_10k_en(v), ha="center", va="bottom")

    axes[1, 1].bar(
        [f"{r.start.date()}\n{r.end.date()}" for r in windows.itertuples(index=False)],
        windows["excess_return"] * 100,
        color="#b05a4a",
    )
    axes[1, 1].set_title("Worst non-overlapping 63D windows")
    axes[1, 1].set_ylabel("fused - static, pct point")
    axes[1, 1].tick_params(axis="x", rotation=45)
    axes[1, 1].grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG / "etf_loop_dynamic_fusion_deep_dive.png")
    plt.close(fig)

    display_cols = ["tag", "annual", "sharpe", "max_dd", "win_rate", "alpha", "beta"]
    final_metric = metric_rows[metric_rows["tag"].isin(final_tags)][display_cols].copy()
    cell_text = []
    for r in final_metric.itertuples(index=False):
        cell_text.append([r.tag, pct(r.annual), f"{r.sharpe:.2f}", pct(r.max_dd), pct(r.win_rate), pct(r.alpha), f"{r.beta:.2f}"])
    fig, ax = plt.subplots(figsize=(13, 4.8))
    ax.axis("off")
    table = ax.table(
        cellText=cell_text,
        colLabels=["Experiment", "Ann", "Sharpe", "DD", "Win", "Alpha", "Beta"],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.35)
    ax.set_title("Final 13Y Metrics (daily CAPM alpha/beta vs HS300)", pad=12)
    fig.tight_layout()
    fig.savefig(FIG / "etf_loop_final13_metrics_table.png")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    name_map = load_name_map()
    static_pool = load_f2_orig_pool()
    dynamic_only = load_g2_union() - static_pool

    static_eq = load_equity(STATIC_TAG)
    fused_eq = load_equity(FUSED_TAG)
    static_trades = load_trades(STATIC_TAG)
    fused_trades = load_trades(FUSED_TAG)

    all_codes = sorted(set(static_trades["ts_code"]) | set(fused_trades["ts_code"]) | static_pool | dynamic_only)
    store = ETFDailyStore(
        SectorProsperityCache(BASE_DIR / "config" / "tushare_token.txt", BASE_DIR / "data" / "tushare_cache"),
        all_codes,
        START,
        END,
    )

    dates = static_eq["date"]
    static_pos = build_position_values(static_trades, dates, store)
    fused_pos = build_position_values(fused_trades, dates, store)

    windows = rolling_worst_windows(static_eq, fused_eq, window=63, n=6)
    all_window_trades = []
    all_exposure = []
    for i, r in enumerate(windows.itertuples(index=False), start=1):
        trades, exposure = summarize_window_trades(
            i, r.start, r.end, static_trades, fused_trades, static_pos, fused_pos, dynamic_only, name_map
        )
        all_window_trades.append(trades)
        all_exposure.append(exposure)

    window_trades = pd.concat(all_window_trades, ignore_index=True) if all_window_trades else pd.DataFrame()
    window_exposure = pd.concat(all_exposure, ignore_index=True) if all_exposure else pd.DataFrame()

    if not window_trades.empty:
        window_trades.to_csv(OUT / "dynamic_pool_worst_window_trades.csv", index=False)
    if not window_exposure.empty:
        window_exposure.to_csv(OUT / "dynamic_pool_worst_window_exposure_delta.csv", index=False)
    windows.to_csv(OUT / "dynamic_pool_worst_windows.csv", index=False)

    manifest = pd.read_csv(OUT / "rerun_manifest.csv")
    metric_rows = []
    manifest_by_tag = manifest.set_index("tag")
    for tag in manifest["tag"]:
        eq = load_equity(tag)
        m = calc_metrics(eq)
        src = manifest_by_tag.loc[tag]
        m.annual = float(src["annual_return"])
        m.sharpe = float(src["sharpe_ratio"])
        m.max_dd = float(src["max_drawdown"])
        m.total = float(src["total_return"])
        m.final_value = float(src["final_value"])
        metric_rows.append({"tag": tag, **m.__dict__})
    metric_df = pd.DataFrame(metric_rows)
    metric_df.to_csv(OUT / "etf_loop_metrics_with_alpha_beta.csv", index=False)

    make_visuals(metric_df, windows)

    report_lines: list[str] = []
    report_lines.append("# ETF Loop 动态池拖累分段交易日志分析\n")
    report_lines.append("对比对象：`FINAL13_F2v3_ORIG38` vs `FINAL13_F2v3_ORIG38_G2PIT`。")
    report_lines.append("分析方法：用 63 个交易日滚动窗口寻找融合策略相对静态 64 池表现最差的非重叠时间段；再回看窗口内交易日志和平均持仓市值差异。")
    report_lines.append("这里的“多买/少买”以窗口内交易净额和窗口平均持仓市值为依据，不是单笔交易因果证明，但能定位动态池抢占仓位发生在哪些时间段、抢了哪些标的。\n")

    report_lines.append("## 1. 最差 63 日窗口\n")
    rows = []
    for r in windows.itertuples(index=False):
        rows.append([r.start.date(), r.end.date(), pct(r.static_return), pct(r.fused_return), pct(r.excess_return)])
    report_lines.append(md_table(["开始", "结束", "静态64收益", "融合收益", "融合-静态"], rows))
    report_lines.append("")

    report_lines.append("## 2. 分窗口交易与持仓变化\n")
    for wid, r in enumerate(windows.itertuples(index=False), start=1):
        report_lines.append(f"### 窗口 {wid}: {r.start.date()} -> {r.end.date()}，融合相对静态 {pct(r.excess_return)}\n")
        ew = window_exposure[window_exposure["window_id"].eq(wid)].copy()
        tw = window_trades[window_trades["window_id"].eq(wid)].copy()

        extra = ew.sort_values("avg_mv_delta_fused_minus_static", ascending=False).head(8)
        rows = [
            [
                x.ts_code,
                x.name,
                "是" if x.is_dynamic_only else "否",
                money(x.static_avg_mv),
                money(x.fused_avg_mv),
                money(x.avg_mv_delta_fused_minus_static),
            ]
            for x in extra.itertuples(index=False)
        ]
        report_lines.append("融合策略平均持仓更多的标的：")
        report_lines.append(md_table(["代码", "ETF 名称", "动态独有", "静态平均市值", "融合平均市值", "融合多配"], rows))
        report_lines.append("")

        missing = ew.sort_values("avg_mv_delta_fused_minus_static").head(8)
        rows = [
            [
                x.ts_code,
                x.name,
                "是" if x.is_dynamic_only else "否",
                money(x.static_avg_mv),
                money(x.fused_avg_mv),
                money(x.avg_mv_delta_fused_minus_static),
            ]
            for x in missing.itertuples(index=False)
        ]
        report_lines.append("融合策略平均持仓更少的标的：")
        report_lines.append(md_table(["代码", "ETF 名称", "动态独有", "静态平均市值", "融合平均市值", "融合少配"], rows))
        report_lines.append("")

        dyn_buys = tw[tw["strategy"].eq("fused_dynamic") & tw["is_dynamic_only"] & tw["action"].eq("BUY")]
        if not dyn_buys.empty:
            agg = dyn_buys.groupby(["ts_code", "name"], as_index=False).agg(
                buy_count=("action", "size"),
                first_buy=("trade_date", "min"),
                last_buy=("trade_date", "max"),
                buy_value=("trade_value", "sum"),
            ).sort_values("buy_value", ascending=False).head(10)
            rows = [
                [x.ts_code, x.name, x.first_buy.date(), x.last_buy.date(), int(x.buy_count), money(x.buy_value)]
                for x in agg.itertuples(index=False)
            ]
            report_lines.append("窗口内融合策略买入的动态独有 ETF：")
            report_lines.append(md_table(["代码", "ETF 名称", "首次买入", "最后买入", "买入次数", "买入净额"], rows))
            report_lines.append("")
        else:
            report_lines.append("窗口内融合策略没有买入动态独有 ETF。\n")

        fused_sells = tw[tw["strategy"].eq("fused_dynamic") & tw["action"].eq("SELL")]
        static_sells = tw[tw["strategy"].eq("static64") & tw["action"].eq("SELL")]
        if not fused_sells.empty:
            agg = fused_sells.groupby(["ts_code", "name", "is_dynamic_only"], as_index=False).agg(
                sell_count=("action", "size"),
                first_sell=("trade_date", "min"),
                last_sell=("trade_date", "max"),
                sell_value=("trade_value", "sum"),
            ).sort_values("sell_value", ascending=False).head(10)
            rows = [
                [x.ts_code, x.name, "是" if x.is_dynamic_only else "否", x.first_sell.date(), x.last_sell.date(), int(x.sell_count), money(x.sell_value)]
                for x in agg.itertuples(index=False)
            ]
            report_lines.append("窗口内融合策略主要卖出：")
            report_lines.append(md_table(["代码", "ETF 名称", "动态独有", "首次卖出", "最后卖出", "卖出次数", "卖出净额"], rows))
            report_lines.append("")
        if not static_sells.empty:
            agg = static_sells.groupby(["ts_code", "name"], as_index=False).agg(
                sell_count=("action", "size"),
                first_sell=("trade_date", "min"),
                last_sell=("trade_date", "max"),
                sell_value=("trade_value", "sum"),
            ).sort_values("sell_value", ascending=False).head(8)
            rows = [
                [x.ts_code, x.name, x.first_sell.date(), x.last_sell.date(), int(x.sell_count), money(x.sell_value)]
                for x in agg.itertuples(index=False)
            ]
            report_lines.append("同窗口静态64策略主要卖出：")
            report_lines.append(md_table(["代码", "ETF 名称", "首次卖出", "最后卖出", "卖出次数", "卖出净额"], rows))
            report_lines.append("")

    report_lines.append("## 3. 总体判断\n")
    report_lines.append("- 动态池纳入后的坏处主要体现为：在若干热点快速轮动阶段，融合策略用动态独有 ETF 或 PIT 新增 ETF 替换了静态池内长期收益更强的标的。")
    report_lines.append("- 动态独有 ETF 不是整体亏损，但它们的平均胜率和平均单笔收益低于静态池内标的，导致新增收益不足以覆盖静态强标的少配损失。")
    report_lines.append("- 这与“防止错过热点”的初衷不矛盾：动态池确实捕捉到了一些新热点，但当前实现让动态候选与静态精选池完全平权竞争 top 5，缺少预算上限和过热惩罚。")
    report_lines.append("- 更合理的下一版应把动态池改成补漏机制，例如最多 1 个席位、最多 20% 权重，或仅当动态标的分数超过静态第 5 名一定安全边际时才允许替换。")
    report_lines.append("")
    report_lines.append("## 4. 图表输出\n")
    report_lines.append("- `outputs/etf_loop/figures/etf_loop_final13_equity_metrics.png`")
    report_lines.append("- `outputs/etf_loop/figures/etf_loop_core_experiment_bars.png`")
    report_lines.append("- `outputs/etf_loop/figures/etf_loop_dynamic_fusion_deep_dive.png`")
    report_lines.append("- `outputs/etf_loop/figures/etf_loop_final13_metrics_table.png`")
    report_lines.append("")
    report_lines.append("## 5. 明细文件\n")
    report_lines.append("- `outputs/etf_loop/dynamic_pool_worst_windows.csv`")
    report_lines.append("- `outputs/etf_loop/dynamic_pool_worst_window_trades.csv`")
    report_lines.append("- `outputs/etf_loop/dynamic_pool_worst_window_exposure_delta.csv`")
    report_lines.append("- `outputs/etf_loop/etf_loop_metrics_with_alpha_beta.csv`")

    (OUT / "dynamic_pool_deep_dive_report.md").write_text("\n".join(report_lines), encoding="utf-8")

    print("Wrote deep-dive report and figures under outputs/etf_loop")
    print(windows.to_string(index=False))


if __name__ == "__main__":
    main()
