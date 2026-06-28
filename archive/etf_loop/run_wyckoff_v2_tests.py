#!/usr/bin/env python3
"""Wyckoff V2 tests: F2_CAP_MA60, F2_STATIC, ORIG38_STATIC × 2026 nowarmup + long period."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = PROJECT_ROOT; sys.path.insert(0, str(PROJECT_ROOT))
import pandas as pd
from strategies.etf_loop_engine import EngineParams, run_and_save
from run_multi_setting_pressure_tests import make_config, load_pit_pool, load_f2_pool
from strategies.etf_loop_strategy import _jq_to_ts, FULL_ETF_POOL_JQ

OUT = BASE_DIR / "outputs" / "etf_loop"; OUT.mkdir(parents=True, exist_ok=True)
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"; REPORT_DIR.mkdir(parents=True, exist_ok=True)
TAG_PREFIX = "WYCKV2_FIX1"
pit = load_pit_pool(); f2p = load_f2_pool()
orig38_p = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ); f2o_p = sorted(set(f2p) | set(orig38_p))

POOL_CONFIGS = {
    "F2_CAP_MA60": {"pit": pit, "f2": f2p, "f2o": f2o_p, "base_cfg": "F2_CAP_MA60", "base_extra": {}},
    "F2_STATIC": {"pit": None, "f2": f2p, "f2o": f2o_p, "base_cfg": "F2_STATIC_BASE", "base_extra": {}},
    "ORIG38_STATIC": {"pit": None, "f2": f2p, "f2o": f2o_p, "base_cfg": "F2_STATIC_BASE",
                      "base_extra": {"etf_pool_ts": orig38_p}},
}

VARIANTS = {
    "Baseline": {},
    "Wyckoff V2 only": {"use_wyckoff_v2": True},
    "Wyckoff V2 + Premium": {"use_wyckoff_v2": True,
                              "use_premium_penalty": True, "premium_penalty": 0.8, "premium_threshold": 0.08},
}

PERIODS = [
    ("LONG_2013_2026", "2013-07-01", "2026-06-25", ""),
    ("2026_NOWARMUP", "2025-10-01", "2026-06-25", "2026-01-02"),
]

rows = []
for period_label, start, end, ts in PERIODS:
    print(f"\n{'='*90}")
    print(f"  {period_label}")
    print(f"{'='*90}")
    for pool_name, pc in POOL_CONFIGS.items():
        print(f"\n  --- {pool_name} ---")
        print(f"  {'Variant':<30s} {'Ann':>8s} {'Sharpe':>7s} {'DD':>8s} {'Final':>14s}")
        print(f"  {'-'*75}")
        for var_name, var_extra in VARIANTS.items():
            tag = f"{TAG_PREFIX}_{pool_name}_{var_name[:20]}_{period_label[:12]}".replace(' ','_').replace('(','').replace(')','')
            extra = {**pc["base_extra"], **var_extra}
            params = make_config(pc["base_cfg"], pc["pit"], pc["f2"], pc["f2o"], tag, extra, start, end)
            params = EngineParams(**{**params.__dict__, "start": start, "end": end, "exp_tag": tag,
                                    "lookback_days": 25, **extra})
            if ts:
                params = EngineParams(**{**params.__dict__, "trading_start": ts})
            sm = OUT / f"etf_loop_summary_{tag}_h5_{start.replace('-','')}_{end.replace('-','')}.csv"
            if sm.exists():
                s = pd.read_csv(sm).iloc[0].to_dict()
            else:
                eq, tr, audit = run_and_save(params, OUT); s = audit["stats"]
            rows.append({"period": period_label, "pool": pool_name, "variant": var_name, "tag": tag, **s})
            print(f"  {var_name:<30s} {s.get('annual_return',0)*100:7.2f}% {s.get('sharpe_ratio',0):6.2f} {s.get('max_drawdown',0)*100:7.2f}% {s.get('final_value',0):>13,.0f}")

df = pd.DataFrame(rows)
csv_path = REPORT_DIR / "wyckoff_v2_fix1.csv"
df.to_csv(csv_path, index=False)
md_path = REPORT_DIR / "wyckoff_v2_fix1.md"
lines = [
    "# Wyckoff V2 FIX1",
    "",
    "- friend_mode: not used",
    "- Wyckoff score logic fixed before rerun",
    "",
    "| period | pool | variant | ann | sharpe | dd | final |",
    "|---|---|---|---:|---:|---:|---:|",
]
for _, r in df.sort_values(["period", "pool", "annual_return"], ascending=[True, True, False]).iterrows():
    lines.append(
        f"| {r['period']} | {r['pool']} | {r['variant']} | {r['annual_return']*100:.2f}% | "
        f"{r['sharpe_ratio']:.2f} | {r['max_drawdown']*100:.2f}% | {r['final_value']:.0f} |"
    )
md_path.write_text("\n".join(lines), encoding="utf-8")
print(f"\nSaved: {csv_path}")
print(f"Saved: {md_path}")
print("\nDone.")
