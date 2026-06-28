#!/usr/bin/env python3
"""Summarize capped dynamic-fusion experiment results."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".matplotlib_cache"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
OUT = BASE_DIR / "outputs" / "etf_loop"
FIG = OUT / "figures"
START = "2013-07-01"
END = "2026-06-25"


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def money(x: float) -> str:
    return "" if pd.isna(x) else f"{x / 10000:.1f}万"


def md_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(str(x) for x in row) + " |" for row in rows)
    return "\n".join(lines)


def output_paths(tag: str) -> tuple[Path, Path]:
    eq = sorted(OUT.glob(f"etf_loop_equity_{tag}_h5_*.csv"))
    tr = sorted(OUT.glob(f"etf_loop_targets_{tag}_h5_*.csv"))
    if not eq or not tr:
        raise FileNotFoundError(tag)
    return eq[0], tr[0]


def extra_metrics(tag: str) -> dict:
    eq_path, trades_path = output_paths(tag)
    eq = pd.read_csv(eq_path, parse_dates=["date"]).sort_values("date")
    ret = eq["portfolio_value"].pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    bench = eq[["date", "benchmark_value"]].dropna()
    bench_ret = bench["benchmark_value"].pct_change().replace([np.inf, -np.inf], np.nan)
    aligned = pd.concat([ret.rename("strategy"), bench_ret.rename("bench")], axis=1).dropna()
    if len(aligned) > 2 and aligned["bench"].var() > 0:
        beta = float(aligned["strategy"].cov(aligned["bench"]) / aligned["bench"].var())
        alpha = float((aligned["strategy"].mean() - beta * aligned["bench"].mean()) * 252)
    else:
        beta = np.nan
        alpha = np.nan

    trades = pd.read_csv(trades_path)
    dyn = trades.get("is_dynamic_only", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)
    buys = trades.get("action", pd.Series("", index=trades.index)).eq("BUY")
    penalized = trades.get("dynamic_overheat_penalized", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)
    gross = pd.to_numeric(trades.get("gross_cost", pd.Series(0.0, index=trades.index)), errors="coerce").fillna(0.0)
    return {
        "win_rate": float((ret > 0).mean()) if len(ret) else np.nan,
        "alpha": alpha,
        "beta": beta,
        "actual_end": eq["date"].max().date().isoformat(),
        "dynamic_buys_check": int((dyn & buys).sum()),
        "dynamic_buy_value_check": float(gross[dyn & buys].sum()),
        "penalized_dynamic_buys_check": int((dyn & buys & penalized).sum()),
    }


def build_table() -> pd.DataFrame:
    rerun = pd.read_csv(OUT / "rerun_manifest.csv")
    capped = pd.read_csv(OUT / "dynamic_fusion_experiment_manifest.csv")

    baseline_tags = [
        ("F2v3", "static", "FINAL13_F2v3", "static F2_v3"),
        ("F2v3", "old_union", "FINAL13_F2v3_G2PIT", "old union: F2_v3 + G2 PIT"),
        ("F2v3_ORIG38", "static", "FINAL13_F2v3_ORIG38", "static F2_v3 + ORIG38"),
        ("F2v3_ORIG38", "old_union", "FINAL13_F2v3_ORIG38_G2PIT", "old union: static64 + G2 PIT"),
    ]
    rows = []
    for group, mode, tag, notes in baseline_tags:
        src = rerun[rerun["tag"].eq(tag)].iloc[0].to_dict()
        rows.append({
            "tag": tag,
            "group": group,
            "mode": mode,
            "notes": notes,
            "annual_return": src["annual_return"],
            "sharpe_ratio": src["sharpe_ratio"],
            "max_drawdown": src["max_drawdown"],
            "total_return": src["total_return"],
            "final_value": src["final_value"],
            "dynamic_buys": np.nan,
            "dynamic_buy_value": np.nan,
            "penalized_dynamic_buys": np.nan,
        })

    for row in capped.to_dict("records"):
        row = dict(row)
        row["mode"] = "capped"
        rows.append(row)

    df = pd.DataFrame(rows)
    extras = pd.DataFrame([{"tag": tag, **extra_metrics(tag)} for tag in df["tag"]])
    df = df.merge(extras, on="tag", how="left")
    df["dynamic_buys"] = df["dynamic_buys"].fillna(df["dynamic_buys_check"])
    df["dynamic_buy_value"] = df["dynamic_buy_value"].fillna(df["dynamic_buy_value_check"])
    df["penalized_dynamic_buys"] = df["penalized_dynamic_buys"].fillna(df["penalized_dynamic_buys_check"])
    df.to_csv(OUT / "dynamic_fusion_capped_metrics.csv", index=False)
    return df


def make_figures(df: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 8, "axes.titlesize": 11, "figure.dpi": 140})

    for group in ["F2v3", "F2v3_ORIG38"]:
        sub = df[df["group"].eq(group)].copy()
        sub = sub.sort_values("annual_return", ascending=True)
        colors = sub["mode"].map({"static": "#4c78a8", "old_union": "#b05a4a", "capped": "#2f855a"}).fillna("#777")
        fig, axes = plt.subplots(1, 2, figsize=(14, max(4, 0.4 * len(sub))))
        axes[0].barh(sub["tag"], sub["annual_return"] * 100, color=colors)
        axes[0].set_title(f"{group}: annual return")
        axes[0].set_xlabel("%")
        axes[0].grid(axis="x", alpha=0.25)
        for i, r in enumerate(sub.itertuples(index=False)):
            axes[0].text(r.annual_return * 100, i, f" S {r.sharpe_ratio:.2f} DD {pct(r.max_drawdown)}", va="center", fontsize=7)

        axes[1].scatter(sub["max_drawdown"] * 100, sub["annual_return"] * 100, s=60, c=colors)
        for r in sub.itertuples(index=False):
            label = r.tag.replace("DYNFUSE_", "").replace(group + "_", "")
            axes[1].annotate(label, (r.max_drawdown * 100, r.annual_return * 100), fontsize=7)
        axes[1].set_title(f"{group}: return vs drawdown")
        axes[1].set_xlabel("max drawdown %")
        axes[1].set_ylabel("annual return %")
        axes[1].grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(FIG / f"dynamic_fusion_capped_{group}.png")
        plt.close(fig)

    capped = df[df["mode"].eq("capped")].copy()
    fig, ax = plt.subplots(figsize=(12, 5))
    for group, marker in [("F2v3", "o"), ("F2v3_ORIG38", "s")]:
        sub = capped[capped["group"].eq(group)]
        ax.scatter(sub["dynamic_buy_value"] / 10000, sub["annual_return"] * 100, label=group, marker=marker, s=70)
        for r in sub.itertuples(index=False):
            label = r.tag.split(group + "_")[-1]
            ax.annotate(label, (r.dynamic_buy_value / 10000, r.annual_return * 100), fontsize=7)
    ax.set_title("Capped dynamic exposure vs annual return")
    ax.set_xlabel("dynamic-only buy value, 10k CNY")
    ax.set_ylabel("annual return %")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "dynamic_fusion_capped_exposure_vs_return.png")
    plt.close(fig)


def write_report(df: pd.DataFrame) -> None:
    lines = ["# ETF Loop capped 动态池融合实验报告\n"]
    lines.append("目的：验证“动态池只作为补漏机制，而不是与静态精选池完全平权竞争 top 5”是否能改善旧双池融合。")
    lines.append("执行命令：`source activate.sh && python runs/etf_loop/run_dynamic_fusion_experiments.py`。")
    lines.append("分析命令：`source activate.sh && python analyze_dynamic_fusion_experiment_results.py`。\n")

    lines.append("## 1. 新机制\n")
    lines.append("- 静态核心池先按原策略选满 5 个名额。")
    lines.append("- 动态 PIT 独有标的最多替换 `dynamic_max_slots` 个名额，本轮主测 1 个名额。")
    lines.append("- 动态 PIT 独有标的总权重最多 `dynamic_max_total_weight`，主测 20%，另测 10%。")
    lines.append("- 动态候选必须超过当前最弱静态入选标的一定分数边际，主测 5%/10%。")
    lines.append("- 动态候选若买入前 20 日涨幅超过阈值，则分数乘以过热惩罚，本轮主测 `prior20d > 10%` 时 `score x 0.5`。")
    lines.append("- 交易执行仍保持修复后的规则：信号日收盘生成订单，次日精确开盘价成交；无次日开盘价就跳过，不 fallback 到信号日收盘价。\n")

    for idx, group in enumerate(["F2v3", "F2v3_ORIG38"], start=2):
        lines.append(f"## {idx}. {group} 结果\n")
        sub = df[df["group"].eq(group)].sort_values("annual_return", ascending=False)
        rows = []
        for r in sub.itertuples(index=False):
            rows.append([
                r.tag,
                r.mode,
                pct(r.annual_return),
                f"{r.sharpe_ratio:.2f}",
                pct(r.max_drawdown),
                pct(r.win_rate),
                pct(r.alpha),
                f"{r.beta:.2f}",
                money(r.final_value),
                int(r.dynamic_buys) if not pd.isna(r.dynamic_buys) else "",
                money(r.dynamic_buy_value) if not pd.isna(r.dynamic_buy_value) else "",
                int(r.penalized_dynamic_buys) if not pd.isna(r.penalized_dynamic_buys) else "",
            ])
        lines.append(md_table([
            "实验", "模式", "年化", "Sharpe", "最大回撤", "日胜率", "Alpha", "Beta",
            "最终资产", "动态买入", "动态买入额", "过热降权买入",
        ], rows))
        lines.append("")

    f2_static = df[df["tag"].eq("FINAL13_F2v3")].iloc[0]
    f2_old = df[df["tag"].eq("FINAL13_F2v3_G2PIT")].iloc[0]
    f2_best = df[df["group"].eq("F2v3") & df["mode"].eq("capped")].sort_values("annual_return", ascending=False).iloc[0]
    f64_static = df[df["tag"].eq("FINAL13_F2v3_ORIG38")].iloc[0]
    f64_old = df[df["tag"].eq("FINAL13_F2v3_ORIG38_G2PIT")].iloc[0]
    f64_best = df[df["group"].eq("F2v3_ORIG38") & df["mode"].eq("capped")].sort_values("annual_return", ascending=False).iloc[0]

    lines.append("## 4. 结论\n")
    lines.append(f"- 对 `F2_v3`，最佳 capped 版本是 `{f2_best.tag}`：年化 {pct(f2_best.annual_return)}，Sharpe {f2_best.sharpe_ratio:.2f}，最大回撤 {pct(f2_best.max_drawdown)}，最终资产 {money(f2_best.final_value)}。")
    lines.append(f"- 它高于静态 `F2_v3` 的年化 {pct(f2_static.annual_return)}，也显著高于旧 union 的年化 {pct(f2_old.annual_return)}。说明对较强但较窄的 44 只 F2_v3 池，动态池作为“有限补漏”是有效的。")
    lines.append(f"- 对 `F2_v3∪ORIG38`，最佳 capped 版本是 `{f64_best.tag}`：年化 {pct(f64_best.annual_return)}，Sharpe {f64_best.sharpe_ratio:.2f}，最终资产 {money(f64_best.final_value)}。")
    lines.append(f"- 它显著优于旧 union 的年化 {pct(f64_old.annual_return)}，但仍低于静态 64 池的年化 {pct(f64_static.annual_return)}。说明静态 64 池已经足够强，动态池即使受限也仍有轻微机会成本。")
    lines.append("- 20 日过热降权对 F2_v3 有正贡献：`H10P50` 系列收益和回撤均优于不降权版本，说明之前确实存在追高噪声。")
    lines.append("- 2 个动态席位即使总权重仍限制在 20%，效果也明显变差，说明“最多 1 个动态补漏席位”比“多动态候选低权重”更稳。")
    lines.append("- 下一步建议把候选默认改成：`dynamic_max_slots=1`、`dynamic_max_total_weight=0.10~0.20`、`dynamic_score_margin=0.05~0.10`、`prior20d>10% score x0.5`。如果主策略采用 F2_v3∪ORIG38，则默认仍建议静态 64，动态池只作为可选增强而非默认。\n")

    lines.append("## 5. 输出文件\n")
    lines.append("- `outputs/etf_loop/dynamic_fusion_experiment_manifest.csv`")
    lines.append("- `outputs/etf_loop/dynamic_fusion_capped_metrics.csv`")
    lines.append("- `outputs/etf_loop/figures/dynamic_fusion_capped_F2v3.png`")
    lines.append("- `outputs/etf_loop/figures/dynamic_fusion_capped_F2v3_ORIG38.png`")
    lines.append("- `outputs/etf_loop/figures/dynamic_fusion_capped_exposure_vs_return.png`")

    (OUT / "dynamic_fusion_capped_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    df = build_table()
    make_figures(df)
    write_report(df)
    print("Saved capped dynamic-fusion metrics/report/figures")


if __name__ == "__main__":
    main()
