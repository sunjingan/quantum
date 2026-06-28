#!/usr/bin/env python3
"""Single-factor follow-up experiments with explicit settings and reproducible tags.

This script reruns only the missing perturbations and loads the already-updated
baseline rows from the current reports.
"""
from __future__ import annotations

import argparse
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
START = "2013-07-01"
END = "2026-06-25"
COST = {"open_cost": 0.00015, "close_cost": 0.00015, "slippage": 0.0002}
LOOKBACK = 25

COMMON_COMMAND = "source activate.sh && python run_single_factor_followups_v1.py"


@dataclass(frozen=True)
class Experiment:
    group: str
    variant: str
    tag: str
    source: str  # "run" or "load"
    start: str = START
    end: str = END
    settings: dict[str, object] | None = None
    source_report: str = ""


def build_base_params(tag: str, start: str = START, end: str = END) -> EngineParams:
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
    return EngineParams(**payload)


def result_paths(tag: str, start: str, end: str) -> tuple[Path, Path, Path]:
    suffix = f"{tag}_h5_{start.replace('-', '')}_{end.replace('-', '')}"
    return (
        OUT / f"etf_loop_equity_{suffix}.csv",
        OUT / f"etf_loop_targets_{suffix}.csv",
        OUT / f"etf_loop_summary_{suffix}.csv",
    )


def load_result(tag: str, start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    eq_path, tr_path, sm_path = result_paths(tag, start, end)
    if not (eq_path.exists() and tr_path.exists() and sm_path.exists()):
        raise FileNotFoundError(f"missing result files for {tag}")
    equity = pd.read_csv(eq_path, parse_dates=["date"]).set_index("date").sort_index()
    trades = pd.read_csv(tr_path)
    stats = pd.read_csv(sm_path).iloc[0].to_dict()
    return equity, trades, stats


def run_result(exp: Experiment) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    params = build_base_params(exp.tag, exp.start, exp.end)
    if not exp.settings:
        raise ValueError(f"missing settings for runnable experiment: {exp.tag}")
    params = EngineParams(**{**params.__dict__, **exp.settings})
    equity, trades, audit = run_and_save(params, OUT)
    stats = audit["stats"]
    stats["trade_count"] = len(trades)
    return equity, trades, stats


def summarize_equity(equity: pd.DataFrame) -> dict[str, object]:
    nav = equity["portfolio_value"].dropna()
    d = nav.pct_change().dropna()
    ann = float(d.mean() * 252.0) if len(d) else np.nan
    dd = float((nav / nav.cummax() - 1.0).min()) if len(nav) else np.nan
    calmar = ann / abs(dd) if dd < 0 else np.nan
    years = {int(y): float(g["portfolio_value"].iloc[-1] / g["portfolio_value"].iloc[0] - 1.0) for y, g in equity.groupby(equity.index.year) if len(g["portfolio_value"].dropna()) >= 2}
    actual_exp = (equity["market_value"] / equity["portfolio_value"]).replace([np.inf, -np.inf], np.nan).dropna()
    cash_ratio = (equity["cash"] / equity["portfolio_value"]).replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "annual_return": ann,
        "max_drawdown": dd,
        "calmar": calmar,
        "year_2018": years.get(2018, np.nan),
        "year_2022": years.get(2022, np.nan),
        "year_2024": years.get(2024, np.nan),
        "avg_actual_exp": float(actual_exp.mean()) if len(actual_exp) else np.nan,
        "avg_cash_ratio": float(cash_ratio.mean()) if len(cash_ratio) else np.nan,
    }


def load_existing_summary_from_file(csv_path: Path, tag: str) -> dict[str, float]:
    df = pd.read_csv(csv_path)
    row = df[df["tag"].eq(tag)]
    if row.empty:
        raise KeyError(f"tag not found in {csv_path}: {tag}")
    return row.iloc[0].to_dict()


def widea_window_experiments() -> list[Experiment]:
    common = {
        "use_market_adaptive_holdings": True,
        "adaptive_mode": "bench_20d_ret",
        "adaptive_tiers_ret": "0.06,0.03,0.00,-0.02,-0.05,-0.08",
        "adaptive_tiers_n": "5,5,4,3,2,1,0",
    }
    return [
        Experiment(
            group="widea_window",
            variant="win_10",
            tag="SF_WIDEA_WIN_10",
            source="run",
            settings={**common, "adaptive_window": 10},
        ),
        Experiment(
            group="widea_window",
            variant="win_15_baseline",
            tag="SEQ_LONG_2013_2026_WideA",
            source="load",
            settings={
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
                "adaptive_window": 15,
                "adaptive_tiers_ret": "0.06,0.03,0.00,-0.02,-0.05,-0.08",
                "adaptive_tiers_n": "5,5,4,3,2,1,0",
            },
            source_report="outputs/etf_loop/F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md",
        ),
        Experiment(
            group="widea_window",
            variant="win_20",
            tag="SF_WIDEA_WIN_20",
            source="run",
            settings={**common, "adaptive_window": 20},
        ),
        Experiment(
            group="widea_window",
            variant="win_30",
            tag="SF_WIDEA_WIN_30",
            source="run",
            settings={**common, "adaptive_window": 30},
        ),
    ]


def widea_threshold_experiments() -> list[Experiment]:
    common = {
        "use_market_adaptive_holdings": True,
        "adaptive_mode": "bench_20d_ret",
        "adaptive_window": 15,
        "adaptive_tiers_n": "5,5,4,3,2,1,0",
    }
    return [
        Experiment(
            group="widea_threshold",
            variant="ret_tighter",
            tag="SF_WIDEA_RET_TIGHTER",
            source="run",
            settings={**common, "adaptive_tiers_ret": "0.07,0.04,0.01,-0.01,-0.04,-0.07"},
        ),
        Experiment(
            group="widea_threshold",
            variant="ret_base",
            tag="SEQ_LONG_2013_2026_WideA",
            source="load",
            settings={
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
                "adaptive_window": 15,
                "adaptive_tiers_ret": "0.06,0.03,0.00,-0.02,-0.05,-0.08",
                "adaptive_tiers_n": "5,5,4,3,2,1,0",
            },
            source_report="outputs/etf_loop/F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md",
        ),
        Experiment(
            group="widea_threshold",
            variant="ret_looser",
            tag="SF_WIDEA_RET_LOOSER",
            source="run",
            settings={**common, "adaptive_tiers_ret": "0.05,0.02,-0.01,-0.03,-0.06,-0.09"},
        ),
    ]


def exph_exposure_experiments() -> list[Experiment]:
    common = {
        "use_market_adaptive_holdings": True,
        "adaptive_mode": "bench_20d_ret",
        "adaptive_window": 15,
        "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
        "adaptive_tiers_n": "5,5,4,4,3,0",
    }
    return [
        Experiment(
            group="exph_exposure",
            variant="exp_conservative",
            tag="SF_EXPH_EXP_CONSERVATIVE",
            source="run",
            settings={**common, "adaptive_tiers_exposure": "1,1,0.80,0.60,0.40,0"},
        ),
        Experiment(
            group="exph_exposure",
            variant="exp_looser_baseline",
            tag="SEQ15D_LONG_2013_2026_Exph_v3_exp_looser",
            source="load",
            settings={
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
                "adaptive_window": 15,
                "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
                "adaptive_tiers_n": "5,5,4,4,3,0",
                "adaptive_tiers_exposure": "1,1,0.85,0.65,0.45,0",
            },
            source_report="outputs/etf_loop/F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md",
        ),
        Experiment(
            group="exph_exposure",
            variant="exp_aggressive",
            tag="SF_EXPH_EXP_AGGRESSIVE",
            source="run",
            settings={**common, "adaptive_tiers_exposure": "1,1,0.90,0.70,0.50,0"},
        ),
    ]


def exph_n_experiments() -> list[Experiment]:
    # Already rerun under the current engine in adaptive_15d_v3_tuning_report.md.
    return [
        Experiment(
            group="exph_n",
            variant="base",
            tag="SEQ15D_LONG_2013_2026_Exph_v3_base",
            source="load",
            settings={
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
                "adaptive_window": 15,
                "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
                "adaptive_tiers_n": "5,5,4,4,3,0",
                "adaptive_tiers_exposure": "1,1,0.80,0.60,0.40,0",
            },
            source_report="outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_15d_v3_tuning_report.md",
        ),
        Experiment(
            group="exph_n",
            variant="n_up1",
            tag="SEQ15D_LONG_2013_2026_Exph_v3_n_up1",
            source="load",
            settings={
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
                "adaptive_window": 15,
                "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
                "adaptive_tiers_n": "5,5,5,4,3,0",
                "adaptive_tiers_exposure": "1,1,0.80,0.60,0.40,0",
            },
            source_report="outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_15d_v3_tuning_report.md",
        ),
        Experiment(
            group="exph_n",
            variant="n_down1",
            tag="SEQ15D_LONG_2013_2026_Exph_v3_n_down1",
            source="load",
            settings={
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
                "adaptive_window": 15,
                "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
                "adaptive_tiers_n": "5,5,4,3,3,0",
                "adaptive_tiers_exposure": "1,1,0.80,0.60,0.40,0",
            },
            source_report="outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_15d_v3_tuning_report.md",
        ),
    ]


def current_score_experiments() -> list[Experiment]:
    common = {
        "use_market_adaptive_holdings": True,
        "adaptive_mode": "bench_20d_ret",
        "adaptive_window": 15,
        "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
        "adaptive_tiers_n": "5,4,3,2,1,0",
    }
    return [
        Experiment(
            group="current_score",
            variant="baseline",
            tag="SEQ_LONG_2013_2026_Current",
            source="load",
            settings={
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
                "adaptive_window": 15,
                "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
                "adaptive_tiers_n": "5,4,3,2,1,0",
                "use_score_weighting": False,
                "switch_score_margin": 0.0,
            },
            source_report="outputs/etf_loop/F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md",
        ),
        Experiment(
            group="current_score",
            variant="score_weighted",
            tag="SF_CURRENT_SCORE_WEIGHTED",
            source="run",
            settings={**common, "use_score_weighting": True},
        ),
        Experiment(
            group="current_score",
            variant="switch_margin_05",
            tag="SF_CURRENT_SWITCH_MARGIN_05",
            source="run",
            settings={**common, "switch_score_margin": 0.05},
        ),
    ]


def build_groups() -> dict[str, list[Experiment]]:
    return {
        "widea_window": widea_window_experiments(),
        "widea_threshold": widea_threshold_experiments(),
        "exph_exposure": exph_exposure_experiments(),
        "exph_n": exph_n_experiments(),
        "current_score": current_score_experiments(),
    }


def collect_experiments(group_name: str | None) -> list[Experiment]:
    groups = build_groups()
    if group_name:
        if group_name not in groups:
            raise KeyError(f"unknown group: {group_name}")
        return groups[group_name]
    out: list[Experiment] = []
    for g in ["widea_window", "widea_threshold", "exph_exposure", "exph_n", "current_score"]:
        out.extend(groups[g])
    return out


def metric_row(exp: Experiment, equity: pd.DataFrame, trades: pd.DataFrame, stats: dict[str, float]) -> dict[str, object]:
    s = summarize_equity(equity)
    row = {
        "group": exp.group,
        "variant": exp.variant,
        "tag": exp.tag,
        "source": exp.source,
        "source_report": exp.source_report,
        "annual_return": float(stats.get("annual_return", s["annual_return"])),
        "sharpe_ratio": float(stats.get("sharpe_ratio", np.nan)),
        "max_drawdown": float(stats.get("max_drawdown", s["max_drawdown"])),
        "calmar": float(stats.get("calmar", s["calmar"])),
        "final_value": float(stats.get("final_value", np.nan)),
        "trade_count": int(stats.get("trade_count", len(trades))),
        "year_2018": s["year_2018"],
        "year_2022": s["year_2022"],
        "year_2024": s["year_2024"],
        "avg_actual_exp": s["avg_actual_exp"],
        "avg_cash_ratio": s["avg_cash_ratio"],
    }
    if exp.settings:
        for k, v in exp.settings.items():
            row[k] = v
    return row


def fmt_pct(v: float) -> str:
    if pd.isna(v):
        return "—"
    return f"{v * 100:.2f}%"


def fmt_num(v: float) -> str:
    if pd.isna(v):
        return "—"
    return f"{v:.2f}"


def fmt_setting(v: object) -> str:
    if v is None:
        return "—"
    try:
        if pd.isna(v):
            return "—"
    except Exception:
        pass
    return str(v)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=["widea_window", "widea_threshold", "exph_exposure", "exph_n", "current_score"], default="")
    args = parser.parse_args()

    experiments = collect_experiments(args.group or None)
    rows: list[dict[str, object]] = []

    for exp in experiments:
        if exp.source == "load":
            equity, trades, stats = load_result(exp.tag, exp.start, exp.end)
        else:
            equity, trades, stats = run_result(exp)
        rows.append(metric_row(exp, equity, trades, stats))

    df = pd.DataFrame(rows)
    df.to_csv(REPORT_DIR / "single_factor_followups_v1_results.csv", index=False)

    report_path = REPORT_DIR / "single_factor_followups_v1_report.md"
    lines = [
        "# Single-Factor Follow-Ups",
        "",
        "## Common Setting",
        f"- pool: `F2_CAP_MA60`",
        f"- benchmark: `{BENCHMARK}`",
        "- period: `2013-07-01` to `2026-06-25`",
        "- cost: `open_cost=0.00015`, `close_cost=0.00015`, `slippage=0.0002`",
        "- execution: signal-day close -> next trading day open, no signal-day close fallback",
        "- control rule: one axis changes at a time; all other strategy knobs stay fixed",
        "",
        "## Repro Command",
        "",
        "```bash",
        f"{COMMON_COMMAND}",
        "```",
        "",
        "You can also run a single group with `--group widea_window`, `--group widea_threshold`, `--group exph_exposure`, `--group exph_n`, or `--group current_score`.",
        "",
        "## Baseline Sources",
        "",
        "- `Current` and `WideA` baselines were refreshed in `outputs/etf_loop/F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md`.",
        "- `Exph_v3_base`, `Exph_v3_n_up1`, `Exph_v3_n_down1` were refreshed in `outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_15d_v3_tuning_report.md`.",
        "",
    ]

    group_meta = {
        "widea_window": {
            "title": "WideA Window Perturbation",
            "setting": "Fix `adaptive_tiers_ret=0.06,0.03,0.00,-0.02,-0.05,-0.08` and `adaptive_tiers_n=5,5,4,3,2,1,0`; vary only `adaptive_window`.",
        },
        "widea_threshold": {
            "title": "WideA Threshold Perturbation",
            "setting": "Fix `adaptive_window=15` and `adaptive_tiers_n=5,5,4,3,2,1,0`; vary only `adaptive_tiers_ret` by one notch.",
        },
        "exph_exposure": {
            "title": "Exph_v3 Exposure Perturbation",
            "setting": "Fix `adaptive_window=15`, `adaptive_tiers_ret=0.05,0.02,0.00,-0.03,-0.06`, `adaptive_tiers_n=5,5,4,4,3,0`; vary only `adaptive_tiers_exposure`.",
        },
        "exph_n": {
            "title": "Exph_v3 N Perturbation",
            "setting": "Already rerun under the current engine; fix `adaptive_window=15` and `adaptive_tiers_exposure=1,1,0.8,0.6,0.4,0`; vary only `adaptive_tiers_n`.",
        },
        "current_score": {
            "title": "Current Score Management",
            "setting": "Fix `adaptive_window=15`, `adaptive_tiers_ret=0.05,0.02,0.00,-0.03,-0.06`, `adaptive_tiers_n=5,4,3,2,1,0`; vary only `use_score_weighting` or `switch_score_margin`.",
        },
    }

    for group in ["widea_window", "widea_threshold", "exph_exposure", "exph_n", "current_score"]:
        g = df[df["group"].eq(group)].copy()
        if g.empty:
            continue
        meta = group_meta[group]
        lines += [
            f"## {meta['title']}",
            "",
            f"- setting: {meta['setting']}",
            f"- repro: `source activate.sh && python run_single_factor_followups_v1.py --group {group}`",
        ]
        if group == "exph_n":
            lines += ["- source report: `adaptive_15d_v3_tuning_report.md`", ""]
        elif group == "current_score":
            lines += ["- source report: `v3_multi_setting_diagnostics.md`", ""]
        elif group in {"widea_window", "widea_threshold", "exph_exposure"}:
            lines += ["- source report: `v3_multi_setting_diagnostics.md`", ""]

        cols = [
            "variant",
            "tag",
            "source",
            "adaptive_window",
            "adaptive_tiers_ret",
            "adaptive_tiers_n",
            "adaptive_tiers_exposure",
            "use_score_weighting",
            "switch_score_margin",
            "annual_return",
            "max_drawdown",
            "sharpe_ratio",
            "calmar",
            "year_2018",
            "year_2022",
            "year_2024",
            "avg_actual_exp",
            "avg_cash_ratio",
            "trade_count",
        ]
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "|".join(["---"] * len(cols)) + "|")
        for _, r in g.iterrows():
            lines.append(
                "| "
                + " | ".join(
                    [
                        fmt_setting(r.get("variant", "")),
                        fmt_setting(r.get("tag", "")),
                        fmt_setting(r.get("source", "")),
                        fmt_setting(r.get("adaptive_window", "")),
                        fmt_setting(r.get("adaptive_tiers_ret", "")),
                        fmt_setting(r.get("adaptive_tiers_n", "")),
                        fmt_setting(r.get("adaptive_tiers_exposure", "")),
                        fmt_setting(r.get("use_score_weighting", "")),
                        fmt_setting(r.get("switch_score_margin", "")),
                        fmt_pct(float(r.get("annual_return", np.nan))),
                        fmt_pct(float(r.get("max_drawdown", np.nan))),
                        fmt_num(float(r.get("sharpe_ratio", np.nan))),
                        fmt_num(float(r.get("calmar", np.nan))),
                        fmt_pct(float(r.get("year_2018", np.nan))),
                        fmt_pct(float(r.get("year_2022", np.nan))),
                        fmt_pct(float(r.get("year_2024", np.nan))),
                        fmt_pct(float(r.get("avg_actual_exp", np.nan))),
                        fmt_pct(float(r.get("avg_cash_ratio", np.nan))),
                        fmt_setting(int(r.get("trade_count", 0))),
                    ]
                )
                + " |"
            )
        lines += ["", "### Notes", ""]
        if group == "widea_window":
            lines += [
                "- This isolates the lookback window only; the threshold ladder and N ladder stay fixed.",
                "- Baseline `win_15` is loaded from the refreshed diagnostics report.",
            ]
        elif group == "widea_threshold":
            lines += [
                "- This isolates the return threshold ladder only; the window and N ladder stay fixed.",
                "- `ret_tighter` shifts every breakpoint up by 1 percentage point; `ret_looser` shifts them down by 1 point.",
            ]
        elif group == "exph_exposure":
            lines += [
                "- This isolates the exposure ladder only; the N ladder stays fixed at `5,5,4,4,3,0`.",
                "- `exp_conservative` is one notch below the current looser variant; `exp_aggressive` is one notch above it.",
            ]
        elif group == "exph_n":
            lines += [
                "- This section is here for completeness because it was already rerun under the fixed engine.",
                "- Compare these rows with `adaptive_15d_v3_tuning_report.md` if you need the full diagnostics.",
            ]
        elif group == "current_score":
            lines += [
                "- `score_weighted` changes only the position sizing rule.",
                "- `switch_margin_05` keeps the same equal-weight sizing but requires a new candidate to beat an existing holding by 5% before switching.",
            ]
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {REPORT_DIR / 'single_factor_followups_v1_results.csv'}")
    print(f"Saved: {report_path}")


if __name__ == "__main__":
    main()
