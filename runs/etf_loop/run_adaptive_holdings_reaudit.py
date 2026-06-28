#!/usr/bin/env python3
"""Re-audit adaptive holdings variants under the current engine.

This script reruns the non-20dRet modes from the adaptive holdings study and
merges them with the already-refreshed 20dRet baseline rows for comparison.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
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
START_LONG = "2013-07-01"
END_LONG = "2026-06-25"
START_NW = "2025-10-01"
END_NW = "2026-06-25"
TRADING_START_NW = "2026-01-02"
COST = {"open_cost": 0.00015, "close_cost": 0.00015, "slippage": 0.0002}
ADAPTIVE_WINDOW = 20
ADAPTIVE_TIERS_RET = "0.05,0.02,0.00,-0.03,-0.06"
ADAPTIVE_TIERS_N = "5,4,3,2,1,0"


@dataclass(frozen=True)
class Experiment:
    period: str
    label: str
    tag: str
    source: str  # run or load
    settings: dict[str, object]
    start: str
    end: str
    trading_start: str = ""
    source_report: str = ""


def build_base_params(tag: str, start: str, end: str) -> EngineParams:
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
        "lookback_days": 25,
    }
    return EngineParams(**payload)


def result_paths(tag: str, start: str, end: str) -> tuple[Path, Path, Path]:
    suffix = f"{tag}_h5_{start.replace('-', '')}_{end.replace('-', '')}"
    return (
        OUT / f"etf_loop_equity_{suffix}.csv",
        OUT / f"etf_loop_targets_{suffix}.csv",
        OUT / f"etf_loop_summary_{suffix}.csv",
    )


def run_exp(exp: Experiment) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    params = build_base_params(exp.tag, exp.start, exp.end)
    params = EngineParams(**{**params.__dict__, **exp.settings})
    if exp.trading_start:
        params = EngineParams(**{**params.__dict__, "trading_start": exp.trading_start})
    equity, trades, audit = run_and_save(params, OUT)
    stats = audit["stats"]
    stats["trade_count"] = len(trades)
    return equity, trades, stats


def load_exp(exp: Experiment) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    eq_path, tr_path, sm_path = result_paths(exp.tag, exp.start, exp.end)
    if not (eq_path.exists() and tr_path.exists() and sm_path.exists()):
        raise FileNotFoundError(f"missing existing result for {exp.tag}")
    equity = pd.read_csv(eq_path, parse_dates=["date"]).set_index("date").sort_index()
    trades = pd.read_csv(tr_path)
    stats = pd.read_csv(sm_path).iloc[0].to_dict()
    return equity, trades, stats


def summarize_equity(equity: pd.DataFrame) -> dict[str, float]:
    nav = equity["portfolio_value"].dropna()
    if len(nav) < 2:
        return {
            "annual_return": np.nan,
            "sharpe_ratio": np.nan,
            "max_drawdown": np.nan,
            "calmar": np.nan,
            "avg_actual_exp": np.nan,
            "avg_cash_ratio": np.nan,
        }
    daily = nav.pct_change().dropna()
    ann = float(daily.mean() * 252.0)
    dd = float((nav / nav.cummax() - 1.0).min())
    actual_exp = (equity["market_value"] / equity["portfolio_value"]).replace([np.inf, -np.inf], np.nan).dropna()
    cash_ratio = (equity["cash"] / equity["portfolio_value"]).replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "annual_return": ann,
        "sharpe_ratio": float(ann / (daily.std() * np.sqrt(252.0))) if len(daily) > 1 and daily.std() > 0 else np.nan,
        "max_drawdown": dd,
        "calmar": float(ann / abs(dd)) if dd < 0 else np.nan,
        "avg_actual_exp": float(actual_exp.mean()) if len(actual_exp) else np.nan,
        "avg_cash_ratio": float(cash_ratio.mean()) if len(cash_ratio) else np.nan,
    }


def fmt_pct(v: float) -> str:
    return "—" if pd.isna(v) else f"{v * 100:.2f}%"


def fmt_num(v: float) -> str:
    return "—" if pd.isna(v) else f"{v:.2f}"


def build_experiments() -> list[Experiment]:
    out: list[Experiment] = []

    # Already refreshed and used as baseline comparison rows.
    for period, start, end, ts, source_report in [
        ("LONG_2013_2026", START_LONG, END_LONG, "", "outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_holdings_fix2_report.md"),
        ("2026_NOWARMUP", START_NW, END_NW, TRADING_START_NW, "outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_holdings_fix2_report.md"),
    ]:
        out.append(
            Experiment(
                period=period,
                label="Baseline fixed 5",
                tag=f"ADAPT2_{period}_Baseline_Fixed5",
                source="load",
                settings={
                    "use_market_adaptive_holdings": False,
                    "use_score_weighting": False,
                    "adaptive_mode": "bench_20d_ret",
                    "adaptive_window": ADAPTIVE_WINDOW,
                    "adaptive_tiers_ret": ADAPTIVE_TIERS_RET,
                    "adaptive_tiers_n": ADAPTIVE_TIERS_N,
                },
                start=start,
                end=end,
                trading_start=ts,
                source_report=source_report,
            )
        )
        out.append(
            Experiment(
                period=period,
                label="20dRet",
                tag=f"ADAPT2_{period}_20dRet",
                source="load",
                settings={
                    "use_market_adaptive_holdings": True,
                    "adaptive_mode": "bench_20d_ret",
                    "adaptive_window": ADAPTIVE_WINDOW,
                    "adaptive_tiers_ret": ADAPTIVE_TIERS_RET,
                    "adaptive_tiers_n": ADAPTIVE_TIERS_N,
                },
                start=start,
                end=end,
                trading_start=ts,
                source_report=source_report,
            )
        )
        out.append(
            Experiment(
                period=period,
                label="20dRet + ScoreW",
                tag=f"ADAPT2_{period}_20dRet_ScoreW",
                source="load",
                settings={
                    "use_market_adaptive_holdings": True,
                    "use_score_weighting": True,
                    "adaptive_mode": "bench_20d_ret",
                    "adaptive_window": ADAPTIVE_WINDOW,
                    "adaptive_tiers_ret": ADAPTIVE_TIERS_RET,
                    "adaptive_tiers_n": ADAPTIVE_TIERS_N,
                },
                start=start,
                end=end,
                trading_start=ts,
                source_report=source_report,
            )
        )
        out.append(
            Experiment(
                period=period,
                label="20dRet + ScoreW + Thresh0.1",
                tag=f"ADAPT2_{period}_20dRet_ScoreW_Thresh01",
                source="load",
                settings={
                    "use_market_adaptive_holdings": True,
                    "use_score_weighting": True,
                    "adaptive_score_threshold": 0.1,
                    "adaptive_mode": "bench_20d_ret",
                    "adaptive_window": ADAPTIVE_WINDOW,
                    "adaptive_tiers_ret": ADAPTIVE_TIERS_RET,
                    "adaptive_tiers_n": ADAPTIVE_TIERS_N,
                },
                start=start,
                end=end,
                trading_start=ts,
                source_report=source_report,
            )
        )

    # Re-run the modes that need a current-engine audit.
    mode_specs = [
        ("MA60", "bench_ma60", None),
        ("Vol", "bench_vol", None),
        ("DD", "portfolio_dd", None),
    ]
    variants = [
        ("base", {}),
        ("scorew", {"use_score_weighting": True}),
        ("scorew_thresh01", {"use_score_weighting": True, "adaptive_score_threshold": 0.1}),
    ]
    for period, start, end, ts in [
        ("LONG_2013_2026", START_LONG, END_LONG, ""),
        ("2026_NOWARMUP", START_NW, END_NW, TRADING_START_NW),
    ]:
        for mode_label, mode_name, _ in mode_specs:
            for variant_name, variant_extra in variants:
                if variant_name == "base":
                    label = mode_label
                    extra = {"use_market_adaptive_holdings": True, "adaptive_mode": mode_name}
                elif variant_name == "scorew":
                    label = f"{mode_label} + ScoreW"
                    extra = {
                        "use_market_adaptive_holdings": True,
                        "adaptive_mode": mode_name,
                        "use_score_weighting": True,
                    }
                else:
                    label = f"{mode_label} + ScoreW + Thresh0.1"
                    extra = {
                        "use_market_adaptive_holdings": True,
                        "adaptive_mode": mode_name,
                        "use_score_weighting": True,
                        "adaptive_score_threshold": 0.1,
                    }
                tag = f"ADAPT_REAUDIT_{period}_{mode_label}_{variant_name}"
                out.append(
                    Experiment(
                        period=period,
                        label=label,
                        tag=tag,
                        source="run",
                        settings={
                            **extra,
                            "adaptive_window": ADAPTIVE_WINDOW,
                            "adaptive_tiers_ret": ADAPTIVE_TIERS_RET,
                            "adaptive_tiers_n": ADAPTIVE_TIERS_N,
                        },
                        start=start,
                        end=end,
                        trading_start=ts,
                        source_report="",
                    )
                )
    return out


def main() -> None:
    exps = build_experiments()
    rows: list[dict[str, object]] = []

    for exp in exps:
        if exp.source == "load":
            equity, trades, stats = load_exp(exp)
        else:
            equity, trades, stats = run_exp(exp)
        s = summarize_equity(equity)
        rows.append(
            {
                "period": exp.period,
                "label": exp.label,
                "tag": exp.tag,
                "source": exp.source,
                "source_report": exp.source_report,
                **exp.settings,
                "annual_return": float(stats.get("annual_return", s["annual_return"])),
                "sharpe_ratio": float(stats.get("sharpe_ratio", s["sharpe_ratio"])),
                "max_drawdown": float(stats.get("max_drawdown", s["max_drawdown"])),
                "calmar": float(stats.get("calmar", s["calmar"])),
                "final_value": float(stats.get("final_value", np.nan)),
                "trade_count": int(stats.get("trade_count", len(trades))),
                "avg_actual_exp": s["avg_actual_exp"],
                "avg_cash_ratio": s["avg_cash_ratio"],
            }
        )

    df = pd.DataFrame(rows)
    csv_path = REPORT_DIR / "adaptive_holdings_reaudit_v1_results.csv"
    df.to_csv(csv_path, index=False)

    report_path = REPORT_DIR / "adaptive_holdings_reaudit_v1_report.md"
    lines = [
        "# Adaptive Holdings Re-Audit",
        "",
        "## Common Setting",
        f"- pool: `F2_CAP_MA60`",
        f"- benchmark: `{BENCHMARK}`",
        f"- costs: commission `1.5bp` + slippage `2bp` per side",
        f"- adaptive window: `{ADAPTIVE_WINDOW}`",
        "- control rule: one market-adaptive axis at a time, fixed baseline as `Baseline fixed 5`",
        "",
        "## Repro Command",
        "",
        "```bash",
        "source activate.sh && python runs/etf_loop/run_adaptive_holdings_reaudit.py",
        "```",
        "",
        "## Source Notes",
        "",
        "- `20dRet` rows are loaded from the refreshed `adaptive_holdings_fix2_report.md` / `adaptive_holdings_fix2_results.csv`.",
        "- `MA60`, `Vol`, and `DD` rows are rerun under the current engine in this pass.",
        "",
    ]
    for period in ["LONG_2013_2026", "2026_NOWARMUP"]:
        g = df[df["period"].eq(period)].copy()
        if g.empty:
            continue
        lines += [
            f"## {period}",
            "",
            "| label | source | adaptive_mode | scoreW | thresh | annual | sharpe | dd | calmar | avg actual exp | avg cash | trades |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for _, r in g.iterrows():
            lines.append(
                f"| {r['label']} | {r['source']} | {r.get('adaptive_mode', 'bench_20d_ret')} | "
                f"{str(r.get('use_score_weighting', False))} | {fmt_num(float(r.get('adaptive_score_threshold', np.nan))) if not pd.isna(r.get('adaptive_score_threshold', np.nan)) else '—'} | "
                f"{fmt_pct(float(r['annual_return']))} | {fmt_num(float(r['sharpe_ratio']))} | {fmt_pct(float(r['max_drawdown']))} | {fmt_num(float(r['calmar']))} | "
                f"{fmt_pct(float(r['avg_actual_exp']))} | {fmt_pct(float(r['avg_cash_ratio']))} | {int(r['trade_count'])} |"
            )
        lines += ["", "### Settings", ""]
        if period == "LONG_2013_2026":
            lines += [
                "- Long-period comparisons use `2013-07-01` to `2026-06-25` with no trading start cutoff.",
            ]
        else:
            lines += [
                "- 2026 nowarmup comparisons use `2025-10-01` to `2026-06-25` and `trading_start=2026-01-02`.",
            ]
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {csv_path}")
    print(f"Saved: {report_path}")


if __name__ == "__main__":
    main()
