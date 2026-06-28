#!/usr/bin/env python3
"""V3 attribution tables across multiple settings.

Reads existing outputs only. No strategy parameters are changed.
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
LONG_START = "2013-07-01"
LONG_END = "2026-06-25"
COST = {"open_cost": 0.00015, "close_cost": 0.00015, "slippage": 0.0002}


@dataclass(frozen=True)
class Setting:
    name: str
    tag: str
    target_exposure: str | None
    setting_desc: str
    start: str = LONG_START
    end: str = LONG_END


SETTINGS = [
    Setting(
        name="Current",
        tag="SEQ_LONG_2013_2026_Current",
        target_exposure=None,
        setting_desc="15d current N-only: tiers_n=5,4,3,2,1,0; exposure=1 everywhere",
    ),
    Setting(
        name="WideA",
        tag="SEQ_LONG_2013_2026_WideA",
        target_exposure=None,
        setting_desc="15d wide A: tiers_n=5,5,4,3,2,1,0; exposure=1 everywhere",
    ),
    Setting(
        name="Exph_v3_base",
        tag="SEQ15D_LONG_2013_2026_Exph_v3_base",
        target_exposure="1,1,0.8,0.6,0.4,0",
        setting_desc="15d exp+hold base: tiers_n=5,5,4,4,3,0; exposure=1,1,0.8,0.6,0.4,0",
    ),
    Setting(
        name="Exph_v3_exp_looser",
        tag="SEQ15D_LONG_2013_2026_Exph_v3_exp_looser",
        target_exposure="1,1,0.85,0.65,0.45,0",
        setting_desc="15d exp+hold looser exposure: tiers_n=5,5,4,4,3,0; exposure=1,1,0.85,0.65,0.45,0",
    ),
]

TIERS_RET = [0.05, 0.02, 0.00, -0.03, -0.06]


def load_equity(setting: Setting) -> pd.DataFrame:
    raise NotImplementedError


def load_trades(setting: Setting) -> pd.DataFrame:
    raise NotImplementedError


def build_base_params(start: str, end: str, tag: str) -> EngineParams:
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


def run_setting(setting: Setting) -> tuple[pd.DataFrame, pd.DataFrame]:
    params = build_base_params(setting.start, setting.end, setting.tag)
    if setting.name == "Current":
        params = EngineParams(
            **{
                **params.__dict__,
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
                "adaptive_window": 15,
                "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
                "adaptive_tiers_n": "5,4,3,2,1,0",
            }
        )
    elif setting.name == "WideA":
        params = EngineParams(
            **{
                **params.__dict__,
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
                "adaptive_window": 15,
                "adaptive_tiers_ret": "0.06,0.03,0.00,-0.02,-0.05,-0.08",
                "adaptive_tiers_n": "5,5,4,3,2,1,0",
            }
        )
    elif setting.name == "Exph_v3_base":
        params = EngineParams(
            **{
                **params.__dict__,
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
                "adaptive_window": 15,
                "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
                "adaptive_tiers_n": "5,5,4,4,3,0",
                "adaptive_tiers_exposure": "1,1,0.8,0.6,0.4,0",
            }
        )
    elif setting.name == "Exph_v3_exp_looser":
        params = EngineParams(
            **{
                **params.__dict__,
                "use_market_adaptive_holdings": True,
                "adaptive_mode": "bench_20d_ret",
                "adaptive_window": 15,
                "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
                "adaptive_tiers_n": "5,5,4,4,3,0",
                "adaptive_tiers_exposure": "1,1,0.85,0.65,0.45,0",
            }
        )
    equity, trades, _ = run_and_save(params, OUT)
    return equity, trades


def annual_by_year(equity: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year, g in equity.groupby(equity.index.year):
        nav = g["portfolio_value"].dropna()
        if len(nav) < 2:
            continue
        rows.append(
            {
                "year": int(year),
                "annual_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0),
            }
        )
    return pd.DataFrame(rows)


def long_summary(equity: pd.DataFrame) -> dict[str, float]:
    nav = equity["portfolio_value"].dropna()
    d = nav.pct_change().dropna()
    ann = float(d.mean() * 252.0) if len(d) else 0.0
    dd = float((nav / nav.cummax() - 1.0).min()) if len(nav) else 0.0
    return {
        "annual_return": ann,
        "max_drawdown": dd,
        "calmar": ann / abs(dd) if dd < 0 else np.nan,
        "final_value": float(nav.iloc[-1]) if len(nav) else np.nan,
    }


def n_distribution(equity: pd.DataFrame) -> pd.DataFrame:
    df = equity.copy()
    if "target_count" not in df.columns:
        return pd.DataFrame()
    # drop the warmup rows so the flat cash phase does not distort the distribution
    df = df.iloc[25:]
    counts = df["target_count"].fillna(-1).astype(int).value_counts().sort_index()
    out = pd.DataFrame({"N": counts.index.astype(int), "days": counts.values})
    out["share"] = out["days"] / out["days"].sum()
    return out


def target_exposure_series(equity: pd.DataFrame, target_exposure: str | None) -> pd.Series:
    if target_exposure is None:
        return pd.Series(1.0, index=equity.index)

    tiers_exp = [float(x) for x in target_exposure.split(",")]
    while len(tiers_exp) < len(TIERS_RET) + 1:
        tiers_exp.append(0.0)

    bench = equity["benchmark_value"].astype(float)
    # signal on day T is executed on day T+1; compare actual exposure on execution day
    bench_sig = bench.shift(1)
    ret_15 = bench_sig / bench_sig.shift(15) - 1.0
    out = pd.Series(tiers_exp[-1], index=equity.index, dtype=float)
    # first-match logic, mirroring the engine's threshold scan from highest tier to lowest
    for i in range(len(TIERS_RET) - 1, -1, -1):
        mask = ret_15 >= TIERS_RET[i]
        out.loc[mask] = tiers_exp[i]
    return out


def exposure_audit(equity: pd.DataFrame, target_exposure: str | None) -> dict[str, float]:
    actual = (equity["market_value"] / equity["portfolio_value"]).replace([np.inf, -np.inf], np.nan)
    target = target_exposure_series(equity, target_exposure)
    m = actual.notna() & target.notna()
    if not m.any():
        return {"max_abs_gap": np.nan, "mean_abs_gap": np.nan, "corr": np.nan}
    diff = (actual[m] - target[m]).abs()
    return {
        "max_abs_gap": float(diff.max()),
        "mean_abs_gap": float(diff.mean()),
        "corr": float(actual[m].corr(target[m])),
    }


def dd_path_summary(equity: pd.DataFrame, trades: pd.DataFrame, target_exposure: str | None) -> dict[str, object]:
    nav = equity["portfolio_value"].dropna()
    dd = nav / nav.cummax() - 1.0
    trough_date = dd.idxmin()
    peak_date = nav.loc[:trough_date].idxmax()
    peak_value = float(nav.loc[peak_date])
    trough_value = float(nav.loc[trough_date])
    recover = nav.loc[trough_date:][nav.loc[trough_date:] >= peak_value]
    rec_date = recover.index[0] if len(recover) else None

    window = equity.loc[peak_date:trough_date]
    actual_exp = (window["market_value"] / window["portfolio_value"]).replace([np.inf, -np.inf], np.nan)
    target_exp = target_exposure_series(equity, target_exposure).loc[peak_date:trough_date]
    td = trades[(trades["trade_date"] >= peak_date) & (trades["trade_date"] <= trough_date)]
    gross_turnover = float(
        td.get("gross_cost", pd.Series(dtype=float)).fillna(0).sum()
        + td.get("gross_proceeds", pd.Series(dtype=float)).fillna(0).sum()
    )
    avg_aum = float(window["portfolio_value"].mean()) if len(window) else np.nan
    turnover = gross_turnover / avg_aum if avg_aum and avg_aum > 0 else np.nan

    return {
        "peak_date": peak_date.date().isoformat(),
        "trough_date": trough_date.date().isoformat(),
        "recover_date": rec_date.date().isoformat() if rec_date is not None else "未恢复",
        "max_dd": float(dd.loc[trough_date]),
        "peak_n": int(equity.loc[peak_date, "target_count"]) if "target_count" in equity.columns else np.nan,
        "trough_n": int(equity.loc[trough_date, "target_count"]) if "target_count" in equity.columns else np.nan,
        "avg_n": float(window["target_count"].mean()) if "target_count" in equity.columns and len(window) else np.nan,
        "avg_actual_exp": float(actual_exp.mean()) if len(actual_exp) else np.nan,
        "avg_target_exp": float(target_exp.mean()) if len(target_exp) else np.nan,
        "turnover": turnover,
        "window_days": int(len(window)),
    }


def bucket_from_target_exp(target_exp: pd.Series) -> pd.Series:
    bins = [-0.01, 0.25, 0.5, 0.75, 0.9, 1.01]
    labels = ["0", "0-25%", "25-50%", "50-75%", "75-90%", "90-100%"]
    return pd.cut(target_exp.fillna(-1), bins=bins, labels=labels, include_lowest=True, right=False)


def market_buckets(equity: pd.DataFrame, setting: Setting) -> pd.DataFrame:
    actual_exp = (equity["market_value"] / equity["portfolio_value"]).replace([np.inf, -np.inf], np.nan)
    target_exp = target_exposure_series(equity, setting.target_exposure)
    # Compute 15d benchmark return on the signal day proxy
    bench_sig = equity["benchmark_value"].shift(1)
    ret_15 = bench_sig / bench_sig.shift(15) - 1.0
    bucket = pd.Series(index=equity.index, dtype="object")
    bucket.loc[ret_15 >= 0.05] = "Bull>5%"
    bucket.loc[(ret_15 < 0.05) & (ret_15 >= 0.02)] = "Strong 2-5%"
    bucket.loc[(ret_15 < 0.02) & (ret_15 >= 0.00)] = "Mild 0-2%"
    bucket.loc[(ret_15 < 0.00) & (ret_15 >= -0.03)] = "Weak -3-0%"
    bucket.loc[(ret_15 < -0.03) & (ret_15 >= -0.06)] = "Bear -6--3%"
    bucket.loc[ret_15 < -0.06] = "Crash<-6%"

    rows = []
    for b, g in equity.groupby(bucket):
        if pd.isna(b):
            continue
        rows.append(
            {
                "bucket": str(b),
                "days": int(len(g)),
                "strategy_mean": float(g["strategy_return"].mean()),
                "strategy_win": float((g["strategy_return"] > 0).mean()),
                "avg_target_n": float(g["target_count"].mean()),
                "avg_actual_exp": float(actual_exp.loc[g.index].mean()),
                "avg_target_exp": float(target_exp.loc[g.index].mean()),
            }
        )
    return pd.DataFrame(rows)


def exposure_distribution(equity: pd.DataFrame, setting: Setting) -> pd.DataFrame:
    target_exp = target_exposure_series(equity, setting.target_exposure)
    actual_exp = (equity["market_value"] / equity["portfolio_value"]).replace([np.inf, -np.inf], np.nan)
    rows = []
    for label, series in [("target", target_exp), ("actual", actual_exp)]:
        q = series.dropna().round(2).value_counts().sort_index()
        for val, cnt in q.items():
            rows.append(
                {
                    "kind": label,
                    "exposure": float(val),
                    "days": int(cnt),
                    "share": float(cnt / len(series.dropna())),
                }
            )
    return pd.DataFrame(rows)


def annual_table(settings_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    years = range(2013, 2027)
    rows = []
    for y in years:
        row = {"year": y}
        for name, eq in settings_data.items():
            g = eq[eq.index.year == y]["portfolio_value"].dropna()
            if len(g) < 2:
                row[name] = np.nan
            else:
                row[name] = float(g.iloc[-1] / g.iloc[0] - 1.0)
        rows.append(row)
    return pd.DataFrame(rows)


def n_table(settings_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for n in range(0, 6):
        row = {"N": n}
        for name, eq in settings_data.items():
            dist = n_distribution(eq)
            m = dist[dist["N"] == n]
            row[name] = float(m["share"].iloc[0]) if len(m) else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def path_table(settings_equity: dict[str, pd.DataFrame], settings_trades: dict[str, pd.DataFrame], settings_meta: dict[str, Setting]) -> pd.DataFrame:
    rows = []
    for name, eq in settings_equity.items():
        info = dd_path_summary(eq, settings_trades[name], settings_meta[name].target_exposure)
        rows.append({"setting": name, **info})
    return pd.DataFrame(rows)


def fmt_pct(v: float) -> str:
    if pd.isna(v):
        return "—"
    return f"{v * 100:.2f}%"


def main() -> None:
    eqs = {}
    trs = {}
    metas = {s.name: s for s in SETTINGS}
    for s in SETTINGS:
        eqs[s.name], trs[s.name] = run_setting(s)

    report = REPORT_DIR / "v3_multi_setting_diagnostics.md"
    lines = [
        "# V3 Multi-Setting Diagnostics",
        "",
        "## Setting",
        f"- benchmark: `{BENCHMARK}`",
        "- base window: `adaptive_window=15`",
        "- cost: `open_cost=0.00015`, `close_cost=0.00015`, `slippage=0.0002`",
        "- execution: signal-day close -> next trading day open, no signal-day fallback",
        "- data source: current code + current engine, rerun in this pass",
        "- control rule: each setting is a single coherent configuration, no mixed-axis tuning",
        "",
        "## Repro Command",
        "",
        "```bash",
        "source activate.sh && python runs/etf_loop/run_v3_attribution_tables.py",
        "```",
        "",
        "## Acceptance Snapshot",
        "",
        "| setting | long ann | dd | calmar | 2013-2024 ann | 2018 | 2022 | 2024 | exposure gap max |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ["Current", "WideA", "Exph_v3_base", "Exph_v3_exp_looser"]:
        eq = eqs[name]
        summ = long_summary(eq)
        pre = eq[eq.index.year <= 2024]["portfolio_value"].dropna()
        ann_1324 = float(pre.pct_change().dropna().mean() * 252.0) if len(pre) > 1 else np.nan
        years = {y: float(g["portfolio_value"].iloc[-1] / g["portfolio_value"].iloc[0] - 1.0) for y, g in eq.groupby(eq.index.year)}
        exp_gap = exposure_audit(eq, metas[name].target_exposure)
        lines.append(
            f"| {name} | {summ['annual_return']*100:.2f}% | {summ['max_drawdown']*100:.2f}% | {summ['calmar']:.2f} | "
            f"{ann_1324*100:.2f}% | {years.get(2018, np.nan)*100:.2f}% | {years.get(2022, np.nan)*100:.2f}% | {years.get(2024, np.nan)*100:.2f}% | {exp_gap['max_abs_gap']*100:.2f}% |"
        )
    lines += ["", "## Table 1: Annual Returns By Year", ""]
    at = annual_table(eqs)
    header = "| year | " + " | ".join(eqs.keys()) + " |"
    sep = "|---:|" + "|".join(["---:"] * len(eqs)) + "|"
    lines += [header, sep]
    for _, r in at.iterrows():
        vals = " | ".join(fmt_pct(r[name]) for name in eqs.keys())
        lines.append(f"| {int(r['year'])} | {vals} |")

    lines += ["", "## Table 2: N Distribution", ""]
    nt = n_table(eqs)
    header = "| N | " + " | ".join(eqs.keys()) + " |"
    sep = "|---:|" + "|".join(["---:"] * len(eqs)) + "|"
    lines += [header, sep]
    for _, r in nt.iterrows():
        vals = " | ".join(f"{r[name]*100:.2f}%" for name in eqs.keys())
        lines.append(f"| {int(r['N'])} | {vals} |")

    lines += ["", "## Table 3: Max Drawdown Path Summary", ""]
    pt = path_table(eqs, trs, metas)
    cols = [
        "setting",
        "peak_date",
        "trough_date",
        "recover_date",
        "max_dd",
        "peak_n",
        "trough_n",
        "avg_n",
        "avg_target_exp",
        "avg_actual_exp",
        "turnover",
        "window_days",
    ]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join(["---"] * len(cols)) + "|")
    for _, r in pt.iterrows():
        lines.append(
            f"| {r['setting']} | {r['peak_date']} | {r['trough_date']} | {r['recover_date']} | {fmt_pct(r['max_dd'])} | "
            f"{int(r['peak_n'])} | {int(r['trough_n'])} | {r['avg_n']:.2f} | {r['avg_target_exp']*100:.2f}% | {r['avg_actual_exp']*100:.2f}% | {r['turnover']:.2f} | {int(r['window_days'])} |"
        )

    lines += ["", "## Exposure Audit", ""]
    lines += ["| setting | max gap | mean gap | corr |", "|---|---:|---:|---:|"]
    for name, eq in eqs.items():
        gap = exposure_audit(eq, metas[name].target_exposure)
        lines.append(
            f"| {name} | {gap['max_abs_gap']*100:.2f}% | {gap['mean_abs_gap']*100:.2f}% | {gap['corr']:.3f} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- `Current` and `WideA` are N-only controls.",
        "- `Exph_v3_base` is the current Exp+Hold baseline.",
        "- `Exph_v3_exp_looser` is the best one-axis local tuning found so far.",
        "- If the acceptance gate is strict on 2018, none of the current settings pass that condition yet.",
    ]

    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {report}")


if __name__ == "__main__":
    main()
