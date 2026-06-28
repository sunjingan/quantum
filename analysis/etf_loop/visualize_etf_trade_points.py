#!/usr/bin/env python3
"""Visualize ETF price curves with strategy buy/sell markers."""
from __future__ import annotations

import argparse
import os
from datetime import timedelta
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".matplotlib_cache"))

import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402


OUT = BASE_DIR / "outputs" / "etf_loop"
CACHE = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity"
FIG_DIR = OUT / "figures" / "trade_points"
START = "20130701"
END = "20260625"

DEFAULT_TAGS = [
    "ABL_F2_CAP_MA_OVERHEAT_MR60_T114_P50",
    "ABL_F2O_CAP_SHORT_MOM_SM0p25",
    "ABL_F2_CAP_ATR_ATR3p0",
    "PERMHOLD_NASDAQ100_HOLDONLY",
    "PERMHOLD_GOLD_HOLDONLY",
]


def setup_fonts() -> None:
    font_paths = [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for path in font_paths:
        if Path(path).exists():
            fm.fontManager.addfont(path)
            prop = fm.FontProperties(fname=path)
            plt.rcParams["font.family"] = prop.get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False


def find_paths(tag: str) -> tuple[Path, Path]:
    targets = sorted(OUT.glob(f"etf_loop_targets_{tag}_h*_{START}_{END}.csv"))
    summaries = sorted(OUT.glob(f"etf_loop_summary_{tag}_h*_{START}_{END}.csv"))
    if not targets:
        raise FileNotFoundError(f"Cannot find targets CSV for {tag}")
    if not summaries:
        raise FileNotFoundError(f"Cannot find summary CSV for {tag}")
    return targets[0], summaries[0]


def load_names() -> dict[str, str]:
    path = CACHE / "fund_basic_etf.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"ts_code": str})
    if "name" not in df.columns:
        return {}
    return dict(zip(df["ts_code"].astype(str), df["name"].astype(str), strict=False))


def choose_codes(trades: pd.DataFrame, top_n: int) -> list[str]:
    buys = trades[trades["action"].astype(str).eq("BUY")].copy()
    if buys.empty:
        return []
    buys["gross_cost"] = pd.to_numeric(buys.get("gross_cost", 0.0), errors="coerce").fillna(0.0)
    score = buys.groupby("ts_code").agg(buy_value=("gross_cost", "sum"), buy_count=("ts_code", "size"))
    score = score.sort_values(["buy_value", "buy_count"], ascending=False)
    return list(score.head(top_n).index.astype(str))


def load_price_series(code: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for path in sorted(CACHE.glob("fund_daily_*.csv")):
        stem = path.stem.replace("fund_daily_", "")
        date = pd.Timestamp(stem)
        if date < start or date > end:
            continue
        df = pd.read_csv(path, dtype={"ts_code": str})
        hit = df[df["ts_code"].eq(code)]
        if hit.empty:
            continue
        r = hit.iloc[0]
        rows.append({
            "date": date,
            "open": pd.to_numeric(r.get("open"), errors="coerce"),
            "close": pd.to_numeric(r.get("close"), errors="coerce"),
            "pct_chg": pd.to_numeric(r.get("pct_chg"), errors="coerce"),
            "amount": pd.to_numeric(r.get("amount"), errors="coerce"),
        })
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values("date").drop_duplicates("date").set_index("date")
    out = out.dropna(subset=["close"])
    if "pct_chg" in out.columns and out["pct_chg"].notna().sum() > 5:
        out["nav"] = (1.0 + out["pct_chg"].fillna(0.0) / 100.0).cumprod()
        out["nav"] = out["nav"] / out["nav"].iloc[0]
    else:
        out["nav"] = out["close"] / out["close"].iloc[0]
    return out


def fmt_pct(x: float) -> str:
    if pd.isna(x):
        return "NA"
    return f"{x * 100:.2f}%"


def plot_one(tag: str, code: str, trades: pd.DataFrame, summary: dict, names: dict[str, str]) -> Path | None:
    code_trades = trades[trades["ts_code"].astype(str).eq(code)].copy()
    if code_trades.empty:
        return None
    code_trades["trade_date"] = pd.to_datetime(code_trades["trade_date"])
    start = code_trades["trade_date"].min().to_pydatetime() - timedelta(days=120)
    end = pd.Timestamp(END)
    prices = load_price_series(code, start, end)
    if prices.empty:
        return None

    buys = code_trades[code_trades["action"].astype(str).eq("BUY")]
    sells = code_trades[code_trades["action"].astype(str).eq("SELL")]
    buy_marks = prices.reindex(pd.to_datetime(buys["trade_date"]).dropna(), method=None).dropna(subset=["nav"])
    sell_marks = prices.reindex(pd.to_datetime(sells["trade_date"]).dropna(), method=None).dropna(subset=["nav"])

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(22, 7))
    ax.plot(prices.index, prices["nav"], color="#222222", linewidth=1.4, label="ETF normalized return curve")
    if not buy_marks.empty:
        ax.scatter(buy_marks.index, buy_marks["nav"], s=18, color="#d62728", edgecolor="white", linewidth=0.35, label="BUY", zorder=3)
    if not sell_marks.empty:
        ax.scatter(sell_marks.index, sell_marks["nav"], s=18, color="#1f77b4", edgecolor="white", linewidth=0.35, label="SELL", zorder=3)

    name = names.get(code, "")
    title = (
        f"{tag}\n{code} {name} | ann {fmt_pct(summary.get('annual_return'))} | "
        f"Sharpe {summary.get('sharpe_ratio', float('nan')):.2f} | DD {fmt_pct(summary.get('max_drawdown'))} | "
        f"buys {len(buys)} sells {len(sells)}"
    )
    ax.set_title(title, fontsize=12)
    ax.set_ylabel("Normalized return curve = 1.0 at first plotted date")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left")
    fig.tight_layout()
    path = FIG_DIR / f"{tag}_{code.replace('.', '')}.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def main() -> None:
    setup_fonts()
    parser = argparse.ArgumentParser(description="Plot ETF close curve with buy/sell markers")
    parser.add_argument("--tags", default=",".join(DEFAULT_TAGS))
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--codes", help="Optional comma-separated ETF codes; if omitted choose top traded ETFs per tag")
    args = parser.parse_args()

    names = load_names()
    saved: list[Path] = []
    for tag in [t.strip() for t in args.tags.split(",") if t.strip()]:
        targets_path, summary_path = find_paths(tag)
        trades = pd.read_csv(targets_path, dtype={"ts_code": str})
        summary = pd.read_csv(summary_path).iloc[0].to_dict()
        codes = [c.strip() for c in args.codes.split(",") if c.strip()] if args.codes else choose_codes(trades, args.top_n)
        for code in codes:
            path = plot_one(tag, code, trades, summary, names)
            if path is not None:
                saved.append(path)
                print("saved", path)

    print(f"Saved {len(saved)} figures under {FIG_DIR}")


if __name__ == "__main__":
    main()
