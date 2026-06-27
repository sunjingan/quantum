#!/usr/bin/env python3
"""15d behavior diagnostics and local V3 tuning under single-factor control."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from run_multi_setting_pressure_tests import make_config, load_f2_pool, load_pit_pool
from strategies.etf_loop_engine import EngineParams, run_and_save
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts


OUT = BASE_DIR / "outputs" / "etf_loop"
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

BENCHMARK = "sh000300"
COST = {"open_cost": 0.00015, "close_cost": 0.00015, "slippage": 0.0002}
LONG_START = "2013-07-01"
LONG_END = "2026-06-25"
LOOKBACK = 25

DIAG_TAGS = {
    "Current": "SEQ_LONG_2013_2026_Current",
    "WideA": "SEQ_LONG_2013_2026_WideA",
    "Exph_v3": "SEQ_LONG_2013_2026_Exph_v3",
}

TUNE_CASES = [
    (
        "Exph_v3_base",
        "base",
        {"adaptive_tiers_n": "5,5,4,4,3,0", "adaptive_tiers_exposure": "1,1,0.8,0.6,0.4,0"},
    ),
    (
        "Exph_v3_n_up1",
        "N_only",
        {"adaptive_tiers_n": "5,5,5,4,3,0", "adaptive_tiers_exposure": "1,1,0.8,0.6,0.4,0"},
    ),
    (
        "Exph_v3_n_down1",
        "N_only",
        {"adaptive_tiers_n": "5,5,4,3,3,0", "adaptive_tiers_exposure": "1,1,0.8,0.6,0.4,0"},
    ),
    (
        "Exph_v3_exp_tighter",
        "Exposure_only",
        {"adaptive_tiers_n": "5,5,4,4,3,0", "adaptive_tiers_exposure": "1,1,0.75,0.55,0.35,0"},
    ),
    (
        "Exph_v3_exp_looser",
        "Exposure_only",
        {"adaptive_tiers_n": "5,5,4,4,3,0", "adaptive_tiers_exposure": "1,1,0.85,0.65,0.45,0"},
    ),
]


def build_base_params(start: str, end: str, tag: str, trading_start: str = "") -> EngineParams:
    pit = load_pit_pool()
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2o = sorted(set(f2) | set(orig38))
    params = make_config("F2_CAP_MA60", pit, f2, f2o, tag, {}, start, end)
    payload = {
        **params.__dict__,
        **COST,
        "benchmark": BENCHMARK,
        "start": start,
        "end": end,
        "exp_tag": tag,
        "lookback_days": LOOKBACK,
    }
    if trading_start:
        payload["trading_start"] = trading_start
    return EngineParams(**payload)


def result_paths(tag: str, start: str, end: str) -> tuple[Path, Path, Path]:
    suffix = f"{tag}_h5_{start.replace('-', '')}_{end.replace('-', '')}"
    return (
        OUT / f"etf_loop_equity_{suffix}.csv",
        OUT / f"etf_loop_targets_{suffix}.csv",
        OUT / f"etf_loop_summary_{suffix}.csv",
    )


def load_or_run(tag: str, start: str, end: str, trading_start: str, extra: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    params = build_base_params(start, end, tag, trading_start)
    params = EngineParams(**{**params.__dict__, **extra})
    eq_path, tr_path, sm_path = result_paths(tag, start, end)
    if eq_path.exists() and tr_path.exists() and sm_path.exists():
        equity = pd.read_csv(eq_path, parse_dates=["date"]).set_index("date").sort_index()
        trades = pd.read_csv(tr_path)
        stats = pd.read_csv(sm_path).iloc[0].to_dict()
        return equity, trades, stats
    equity, trades, audit = run_and_save(params, OUT)
    stats = audit["stats"]
    stats["trade_count"] = len(trades)
    return equity, trades, stats


def annual_table(equity: pd.DataFrame) -> pd.DataFrame:
    if equity.empty:
        return pd.DataFrame()
    df = equity.copy().sort_index().iloc[LOOKBACK:]
    if "portfolio_value" not in df.columns:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for year, g in df.groupby(df.index.year):
        nav = g["portfolio_value"].dropna()
        if len(nav) < 2:
            continue
        rows.append(
            {
                "year": int(year),
                "annual_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0),
                "max_drawdown": float((nav / nav.cummax() - 1.0).min()),
                "days": int(len(nav)),
            }
        )
    return pd.DataFrame(rows)


def n_distribution(equity: pd.DataFrame) -> pd.DataFrame:
    df = equity.copy().sort_index()
    if "target_count" not in df.columns:
        return pd.DataFrame()
    df = df.iloc[LOOKBACK:]
    counts = df["target_count"].fillna(-1).astype(int).value_counts().sort_index()
    out = pd.DataFrame({"N": counts.index.astype(int), "days": counts.values})
    out["share"] = out["days"] / out["days"].sum()
    return out


def forward_return_by_n(equity: pd.DataFrame, source_col: str, horizons: list[int]) -> pd.DataFrame:
    df = equity.copy().sort_index()
    if source_col not in df.columns or "target_count" not in df.columns:
        return pd.DataFrame()
    df = df.iloc[LOOKBACK:].copy()
    rows: list[dict[str, object]] = []
    for h in horizons:
        fwd = df[source_col].shift(-h) / df[source_col] - 1.0
        tmp = df.assign(_fwd=fwd).dropna(subset=["_fwd"])
        for n, g in tmp.groupby("target_count"):
            rows.append(
                {
                    "horizon": h,
                    "N": int(n),
                    "count": int(len(g)),
                    "mean": float(g["_fwd"].mean()),
                    "median": float(g["_fwd"].median()),
                }
            )
    return pd.DataFrame(rows)


def build_behavior_report(lines: list[str], name: str, equity: pd.DataFrame, trades: pd.DataFrame) -> None:
    lines += [f"## {name}", ""]
    a = annual_table(equity)
    if not a.empty:
        lines += ["### Annual By Year", "", "| year | annual | dd | days |", "|---:|---:|---:|---:|"]
        for _, r in a.iterrows():
            lines.append(f"| {int(r['year'])} | {r['annual_return']*100:.2f}% | {r['max_drawdown']*100:.2f}% | {int(r['days'])} |")
        lines.append("")
    nd = n_distribution(equity)
    if not nd.empty:
        lines += ["### N Distribution", "", "| N | days | share |", "|---:|---:|---:|"]
        for _, r in nd.iterrows():
            lines.append(f"| {int(r['N'])} | {int(r['days'])} | {r['share']*100:.2f}% |")
        lines.append("")
    for col, label in [("portfolio_value", "Portfolio"), ("benchmark_value", "Benchmark")]:
        fr = forward_return_by_n(equity, col, [5, 10, 20])
        if fr.empty:
            continue
        lines += [f"### Forward {label} Return By N", "", "| horizon | N | count | mean | median |", "|---:|---:|---:|---:|---:|"]
        for _, r in fr.sort_values(["horizon", "N"]).iterrows():
            lines.append(
                f"| {int(r['horizon'])} | {int(r['N'])} | {int(r['count'])} | {r['mean']*100:.2f}% | {r['median']*100:.2f}% |"
            )
        lines.append("")
    if not trades.empty:
        action = trades.get("action", pd.Series("", index=trades.index)).astype(str)
        lines += [
            "### Trading Summary",
            "",
            f"- trades: {int(len(trades))}",
            f"- buys: {int((action == 'BUY').sum())}",
            f"- sells: {int((action == 'SELL').sum())}",
            "",
        ]


def run_tuning_case(period: str, start: str, end: str, trading_start: str, label: str, axis: str, extra: dict) -> dict:
    tag = f"SEQ15D_{period}_{label}"
    equity, trades, stats = load_or_run(tag, start, end, trading_start, {
        "use_market_adaptive_holdings": True,
        "adaptive_mode": "bench_20d_ret",
        "adaptive_window": 15,
        **extra,
    })
    return {
        "period": period,
        "variant": label,
        "axis": axis,
        "tag": tag,
        "annual_return": stats.get("annual_return", 0.0),
        "sharpe_ratio": stats.get("sharpe_ratio", 0.0),
        "max_drawdown": stats.get("max_drawdown", 0.0),
        "final_value": stats.get("final_value", 0.0),
        "trade_count": int(stats.get("trade_count", len(trades))),
    }


def main() -> None:
    report_path = REPORT_DIR / "adaptive_15d_v3_tuning_report.md"
    csv_path = REPORT_DIR / "adaptive_15d_v3_tuning_results.csv"
    lines = [
        "# 15D Behavior Diagnostics and V3 Local Tuning",
        "",
        "## Setting",
        f"- pool: `F2_CAP_MA60`",
        f"- benchmark: `{BENCHMARK}`",
        "- window: `adaptive_window=15`",
        "- cost: commission `1.5bp` + slippage `2bp` per side",
        "- execution: signal-day close -> next trading day open, no signal-day close fallback",
        "- control rule: diagnostics only read existing outputs; tuning block changes one axis at a time",
        "",
        "## Repro Command",
        "",
        "```bash",
        "source activate.sh && python run_15d_behavior_v3_tuning.py",
        "```",
        "",
        "## Diagnostics Source",
        "",
        "- `SEQ_LONG_2013_2026_Current`",
        "- `SEQ_LONG_2013_2026_WideA`",
        "- `SEQ_LONG_2013_2026_Exph_v3`",
        "",
    ]

    # Diagnostics from existing outputs
    lines += ["## 15D Behavior Diagnostics", ""]
    for name, tag in DIAG_TAGS.items():
        eq_path, tr_path, sm_path = result_paths(tag, LONG_START, LONG_END)
        if not (eq_path.exists() and tr_path.exists() and sm_path.exists()):
            raise FileNotFoundError(f"missing diagnostic output for {name}: {tag}")
        equity = pd.read_csv(eq_path, parse_dates=["date"]).set_index("date").sort_index()
        trades = pd.read_csv(tr_path)
        build_behavior_report(lines, name, equity, trades)

    # Local tuning
    rows: list[dict] = []
    periods = [
        ("LONG_2013_2026", LONG_START, LONG_END, ""),
        ("2026_NOWARMUP", "2025-10-01", LONG_END, "2026-01-02"),
    ]
    for period, start, end, trading_start in periods:
        lines += [f"## Local Tuning: {period}", ""]
        lines += [
            "- base: `adaptive_window=15`, `adaptive_mode=bench_20d_ret`, `F2_CAP_MA60`",
            "- only one axis is changed per variant",
            "",
        ]

        n_variants = [
            ("Exph_v3_base", "N", {"adaptive_tiers_n": "5,5,4,4,3,0", "adaptive_tiers_exposure": "1,1,0.8,0.6,0.4,0"}),
            ("Exph_v3_n_up1", "N", {"adaptive_tiers_n": "5,5,5,4,3,0", "adaptive_tiers_exposure": "1,1,0.8,0.6,0.4,0"}),
            ("Exph_v3_n_down1", "N", {"adaptive_tiers_n": "5,5,4,3,3,0", "adaptive_tiers_exposure": "1,1,0.8,0.6,0.4,0"}),
        ]
        exp_variants = [
            ("Exph_v3_exp_tighter", "Exposure", {"adaptive_tiers_n": "5,5,4,4,3,0", "adaptive_tiers_exposure": "1,1,0.75,0.55,0.35,0"}),
            ("Exph_v3_exp_looser", "Exposure", {"adaptive_tiers_n": "5,5,4,4,3,0", "adaptive_tiers_exposure": "1,1,0.85,0.65,0.45,0"}),
        ]
        for label, axis, extra in n_variants + exp_variants:
            rows.append(run_tuning_case(period, start, end, trading_start, label, axis, extra))

        sub = pd.DataFrame([r for r in rows if r["period"] == period])
        lines += ["| variant | axis | annual | sharpe | dd | trades |", "|---|---|---:|---:|---:|---:|"]
        for _, r in sub.sort_values("annual_return", ascending=False).iterrows():
            lines.append(
                f"| {r['variant']} | {r['axis']} | {r['annual_return']*100:.2f}% | {r['sharpe_ratio']:.2f} | "
                f"{r['max_drawdown']*100:.2f}% | {int(r['trade_count'])} |"
            )
        lines.append("")

        base = sub[sub["variant"] == "Exph_v3_base"].iloc[0]
        lines += [
            f"- baseline control: annual {base['annual_return']*100:.2f}%, sharpe {base['sharpe_ratio']:.2f}, dd {base['max_drawdown']*100:.2f}%",
            "",
        ]

    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)
    lines += [
        "## Notes",
        "",
        "- diagnostics are descriptive only; they do not change parameters",
        "- tuning variants are single-axis perturbations around `Exph_v3`",
        "- keep `15d` fixed throughout this script",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {csv_path}")
    print(f"Saved: {report_path}")


if __name__ == "__main__":
    main()
