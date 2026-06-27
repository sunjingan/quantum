#!/usr/bin/env python3
"""Ordered adaptive holdings sequence: window scan -> thresholds -> WideA/B -> V3 exp/hold split."""
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

COST = {"open_cost": 0.00015, "close_cost": 0.00015, "slippage": 0.0002}
BENCHMARK = "sh000300"
PERIODS = [
    ("2026_NOWARMUP", "2025-10-01", "2026-06-25", "2026-01-02"),
    ("LONG_2013_2026", "2013-07-01", "2026-06-25", ""),
]


def suffix(tag: str, start: str, end: str) -> str:
    return f"{tag}_h5_{start.replace('-', '')}_{end.replace('-', '')}"


def load_params_base(start: str, end: str, tag: str) -> EngineParams:
    pit = load_pit_pool()
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2o = sorted(set(f2) | set(orig38))
    params = make_config("F2_CAP_MA60", pit, f2, f2o, tag, {}, start, end)
    return EngineParams(
        **{
            **params.__dict__,
            **COST,
            "benchmark": BENCHMARK,
            "start": start,
            "end": end,
            "exp_tag": tag,
            "lookback_days": 25,
        }
    )


def run_case(tag: str, start: str, end: str, extra: dict) -> dict:
    params = load_params_base(start, end, tag)
    params = EngineParams(**{**params.__dict__, **extra})
    eq_path = OUT / f"etf_loop_equity_{suffix(tag, start, end)}.csv"
    tr_path = OUT / f"etf_loop_targets_{suffix(tag, start, end)}.csv"
    sm_path = OUT / f"etf_loop_summary_{suffix(tag, start, end)}.csv"
    if eq_path.exists() and tr_path.exists() and sm_path.exists():
        stats = pd.read_csv(sm_path).iloc[0].to_dict()
    else:
        _, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]
        stats["trade_count"] = len(trades)
    return stats


def write_table(path: Path, title: str, rows: list[dict], cols: list[str]) -> None:
    lines = [f"# {title}", ""]
    if rows:
        header = "| " + " | ".join(cols) + " |"
        sep = "| " + " | ".join(["---"] * len(cols)) + " |"
        lines += [header, sep]
        for r in rows:
            lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    else:
        lines.append("_empty_")
    path.write_text("\n".join(lines), encoding="utf-8")


def fmt_pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def main() -> None:
    rows: list[dict] = []

    # 1) Window scan
    window_scan = [5, 10, 15, 20, 30, 60]
    for period_label, start, end, trading_start in PERIODS:
        print(f"\n{'=' * 90}")
        print(f"  {period_label} - 20dRet window scan")
        print(f"{'=' * 90}")
        for w in window_scan:
            tag = f"SEQ_{period_label}_WIN_{w}"
            extra = {
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
                "adaptive_window": w,
            }
            if trading_start:
                extra["trading_start"] = trading_start
            s = run_case(tag, start, end, extra)
            rows.append(
                {
                    "group": "window_scan",
                    "period": period_label,
                    "variant": f"{w}d",
                    "annual_return": s.get("annual_return", 0.0),
                    "sharpe_ratio": s.get("sharpe_ratio", 0.0),
                    "max_drawdown": s.get("max_drawdown", 0.0),
                    "final_value": s.get("final_value", 0.0),
                    "trade_count": s.get("trade_count", 0),
                }
            )
            print(f"  {w:>2d}d  ann={fmt_pct(s.get('annual_return',0))} sharpe={s.get('sharpe_ratio',0):.2f} dd={fmt_pct(s.get('max_drawdown',0))} trades={s.get('trade_count',0)}")

    # 2) Baseline score-threshold tests
    threshold_cases = [
        ("Dynamic ratio 0.5", {"use_dynamic_score_threshold": True, "dynamic_score_threshold_ratio": 0.5}),
        ("Fixed threshold 0.1", {"adaptive_score_threshold": 0.1}),
        ("Rolling P60", {"use_rolling_score_threshold": True, "rolling_score_window": 252}),
    ]
    # Baseline control is fixed 5; only rolling threshold is expected to have effect.
    for period_label, start, end, trading_start in PERIODS:
        print(f"\n{'=' * 90}")
        print(f"  {period_label} - baseline threshold control")
        print(f"{'=' * 90}")
        for label, extra in threshold_cases:
            tag = f"SEQ_{period_label}_{label[:24].replace(' ', '_').replace('.', '')}"
            payload = {"use_market_adaptive_holdings": False, "use_score_weighting": False}
            payload.update(extra)
            if trading_start:
                payload["trading_start"] = trading_start
            s = run_case(tag, start, end, payload)
            rows.append(
                {
                    "group": "threshold_baseline",
                    "period": period_label,
                    "variant": label,
                    "annual_return": s.get("annual_return", 0.0),
                    "sharpe_ratio": s.get("sharpe_ratio", 0.0),
                    "max_drawdown": s.get("max_drawdown", 0.0),
                    "final_value": s.get("final_value", 0.0),
                    "trade_count": s.get("trade_count", 0),
                }
            )
            print(f"  {label:<20s} ann={fmt_pct(s.get('annual_return',0))} sharpe={s.get('sharpe_ratio',0):.2f} dd={fmt_pct(s.get('max_drawdown',0))}")

    # 3) Wide A/B and current control
    wide_cases = [
        ("Current", {"adaptive_window": 15, "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06", "adaptive_tiers_n": "5,4,3,2,1,0"}),
        ("WideA", {"adaptive_window": 15, "adaptive_tiers_ret": "0.06,0.03,0.00,-0.02,-0.05,-0.08", "adaptive_tiers_n": "5,5,4,3,2,1,0"}),
        ("WideB", {"adaptive_window": 15, "adaptive_tiers_ret": "0.05,0.01,-0.02,-0.05,-0.08,-0.12", "adaptive_tiers_n": "5,5,4,3,2,1,0"}),
    ]
    for period_label, start, end, trading_start in PERIODS:
        print(f"\n{'=' * 90}")
        print(f"  {period_label} - wide A/B")
        print(f"{'=' * 90}")
        for label, extra in wide_cases:
            tag = f"SEQ_{period_label}_{label}"
            payload = {
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
            }
            payload.update(extra)
            if trading_start:
                payload["trading_start"] = trading_start
            s = run_case(tag, start, end, payload)
            rows.append(
                {
                    "group": "wide_ab",
                    "period": period_label,
                    "variant": label,
                    "annual_return": s.get("annual_return", 0.0),
                    "sharpe_ratio": s.get("sharpe_ratio", 0.0),
                    "max_drawdown": s.get("max_drawdown", 0.0),
                    "final_value": s.get("final_value", 0.0),
                    "trade_count": s.get("trade_count", 0),
                }
            )
            print(f"  {label:<10s} ann={fmt_pct(s.get('annual_return',0))} sharpe={s.get('sharpe_ratio',0):.2f} dd={fmt_pct(s.get('max_drawdown',0))}")

    # 4) V3 exp/hold split
    v3_cases = [
        ("Exph_base", {"adaptive_window": 15, "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06", "adaptive_tiers_n": "5,4,4,3,3,0", "adaptive_tiers_exposure": "1,1,0.8,0.6,0.4,0"}),
        ("Exph_v2_lower_bear", {"adaptive_window": 15, "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06", "adaptive_tiers_n": "5,4,4,3,3,0", "adaptive_tiers_exposure": "1,1,0.7,0.5,0.2,0"}),
        ("Exph_v3", {"adaptive_window": 15, "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06", "adaptive_tiers_n": "5,5,4,4,3,0", "adaptive_tiers_exposure": "1,1,0.8,0.6,0.4,0"}),
        ("Exph_v4_smoother", {"adaptive_window": 15, "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06", "adaptive_tiers_n": "5,4,4,3,3,0", "adaptive_tiers_exposure": "1,1,0.85,0.65,0.45,0"}),
        ("Exph_v5_div_lowbear", {"adaptive_window": 15, "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06", "adaptive_tiers_n": "5,5,4,3,3,0", "adaptive_tiers_exposure": "1,1,0.7,0.5,0.2,0"}),
        ("Exph_v6_very_high_div", {"adaptive_window": 15, "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06", "adaptive_tiers_n": "5,5,5,4,3,0", "adaptive_tiers_exposure": "1,1,0.8,0.6,0.4,0"}),
    ]
    for period_label, start, end, trading_start in PERIODS:
        print(f"\n{'=' * 90}")
        print(f"  {period_label} - V3 exp/hold split")
        print(f"{'=' * 90}")
        for label, extra in v3_cases:
            tag = f"SEQ_{period_label}_{label}"
            payload = {
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
            }
            payload.update(extra)
            if trading_start:
                payload["trading_start"] = trading_start
            s = run_case(tag, start, end, payload)
            rows.append(
                {
                    "group": "v3_exp_hold",
                    "period": period_label,
                    "variant": label,
                    "annual_return": s.get("annual_return", 0.0),
                    "sharpe_ratio": s.get("sharpe_ratio", 0.0),
                    "max_drawdown": s.get("max_drawdown", 0.0),
                    "final_value": s.get("final_value", 0.0),
                    "trade_count": s.get("trade_count", 0),
                }
            )
            print(f"  {label:<20s} ann={fmt_pct(s.get('annual_return',0))} sharpe={s.get('sharpe_ratio',0):.2f} dd={fmt_pct(s.get('max_drawdown',0))}")

    df = pd.DataFrame(rows)
    csv_path = REPORT_DIR / "adaptive_sequence_v3_results.csv"
    df.to_csv(csv_path, index=False)

    report_path = REPORT_DIR / "adaptive_sequence_v3_report.md"
    lines = [
        "# Adaptive Sequence V3",
        "",
        f"- benchmark: `{BENCHMARK}`",
        "- cost: 1.5bp commission + 2bp slippage per side",
        "- order: window scan -> baseline threshold controls -> wide A/B -> V3 exp/hold split",
        "",
    ]
    for group in ["window_scan", "threshold_baseline", "wide_ab", "v3_exp_hold"]:
        g = df[df["group"] == group].copy()
        if g.empty:
            continue
        lines += [
            f"## {group}",
            "",
            "| period | variant | annual | sharpe | dd | final | trades |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
        for _, r in g.sort_values(["period", "annual_return"], ascending=[True, False]).iterrows():
            lines.append(
                f"| {r['period']} | {r['variant']} | {r['annual_return']*100:.2f}% | "
                f"{r['sharpe_ratio']:.2f} | {r['max_drawdown']*100:.2f}% | {r['final_value']:,.0f} | {int(r['trade_count'])} |"
            )
        lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved: {csv_path}")
    print(f"Saved: {report_path}")


if __name__ == "__main__":
    main()
