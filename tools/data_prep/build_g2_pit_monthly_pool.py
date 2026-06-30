#!/usr/bin/env python3
"""Rebuild the G2 point-in-time monthly ETF pool from local Tushare cache.

The output is a dict: {month_end_timestamp: [ts_code, ...]}.  Each month-end
pool is meant to be used by the following month in the backtest engine through
the existing "last month_end <= signal_date" lookup.

No network calls are made.  The script consumes:
  data/tushare_cache/sector_prosperity/fund_basic_etf.csv
  data/tushare_cache/sector_prosperity/fund_daily_YYYYMMDD.csv
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

PURE_BROAD_BENCHMARKS = [
    "沪深300", "中证500", "中证1000", "中证2000",
    "中证A500", "中证A100", "中证A50",
    "上证50", "上证180", "上证380", "上海证券交易所50成份",
    "深证100", "深证300", "深证50",
    "创业板指", "创业板50", "创业板综",
    "科创50", "科创100", "科创综指", "科创板50",
    "北证50",
    "中证小盘500",
]
BROAD_OVERRIDES = {
    "510050.SH",
    "510500.SH",
}
STYLE_KW = [
    "红利", "价值", "低波", "银行", "高股息", "现金流", "质量",
]
COMMODITY_KW = [
    "黄金", "白银", "原油", "期货", "有色", "豆粕", "能源化工",
]
THEME_EXCLUDE_KW = [
    "半导体", "芯片", "通信设备", "通信", "5G", "人工智能", "AI", "机器人",
    "电网", "电力", "卫星", "军工", "新能源", "光伏", "电池",
    "汽车", "医药", "医疗", "创新药", "消费", "食品", "饮料",
    "酒", "煤炭", "钢铁", "有色", "化工", "农业", "证券", "券商",
    "保险", "地产", "房地产", "基建", "传媒", "游戏", "软件",
    "科技", "工业", "制造",
]


DEFAULT_CACHE = PROJECT_ROOT / "data" / "tushare_cache"
SECTOR_DIR = DEFAULT_CACHE / "sector_prosperity"

G2_BUCKET_QUOTAS = {
    "defensive": 4,
    "commodity": 5,
    "overseas_us": 4,
    "hk_china": 3,
    "other_overseas": 2,
    "broad_a": 6,
    "style": 6,
    "theme": 5,
}

CANONICAL_CODES = {
    "513100.SH",  # 纳指
    "513500.SH",  # 标普
    "513400.SH",  # 道琼斯
    "513520.SH",  # 日经
    "518880.SH",  # 黄金
    "518850.SH",  # 黄金
    "511880.SH",  # 货币
    "511990.SH",  # 货币
    "159915.SZ",  # 创业板
    "510050.SH",  # 上证50
    "510500.SH",  # 中证500
    "159919.SZ",  # 沪深300
}

US_OVERSEAS_KW = ["纳斯达克", "标普", "道琼斯", "日经"]
HK_CHINA_KW = ["恒生", "恒科", "中概", "港股", "香港", "中国互联网", "中韩"]
OTHER_OVERSEAS_KW = ["QDII", "东南亚", "印度", "德国", "法国", "海外", "全球"]


def parse_ymd_scalar(value: Any) -> pd.Timestamp:
    if pd.isna(value):
        return pd.NaT
    text = str(value).replace(".0", "")
    return pd.to_datetime(text, format="%Y%m%d", errors="coerce")


def parse_ymd_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(
        s.astype(str).str.replace(r"\.0$", "", regex=True),
        format="%Y%m%d",
        errors="coerce",
    )


def is_pure_broad(benchmark: str, name: str) -> bool:
    combined = f"{benchmark}{name}"
    if any(kw in combined for kw in THEME_EXCLUDE_KW):
        return False
    return any(kw in benchmark for kw in PURE_BROAD_BENCHMARKS)


def classify_g2_bucket(ts_code: str, name: str, fund_type: str, benchmark: str) -> str:
    """G2 classification with overseas split into US/HK/Other sub-buckets."""
    combined = f"{benchmark}{name}"
    if ts_code in BROAD_OVERRIDES:
        return "broad_a"
    if fund_type in ("债券型", "货币型"):
        return "defensive"
    if any(kw in combined for kw in COMMODITY_KW):
        return "commodity"
    if any(kw in combined for kw in US_OVERSEAS_KW):
        return "overseas_us"
    if any(kw in combined for kw in HK_CHINA_KW):
        return "hk_china"
    if "QDII" in name or "QDII" in benchmark or any(kw in combined for kw in OTHER_OVERSEAS_KW):
        return "other_overseas"
    if any(kw in combined for kw in STYLE_KW):
        return "style"
    if is_pure_broad(benchmark, name):
        return "broad_a"
    return "theme"


def load_fund_basic(sector_dir: Path) -> pd.DataFrame:
    path = sector_dir / "fund_basic_etf.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, dtype={"ts_code": str})
    df = df[df["ts_code"].astype(str).str.endswith((".SH", ".SZ"))].copy()
    df["ts_code"] = df["ts_code"].astype(str)
    df["name"] = df["name"].fillna("").astype(str)
    df["benchmark"] = df["benchmark"].fillna("").astype(str)
    df["fund_type"] = df["fund_type"].fillna(df.get("type", "")).fillna("").astype(str)
    df["list_date_dt"] = parse_ymd_series(df["list_date"])
    if "delist_date" in df.columns:
        df["delist_date_dt"] = parse_ymd_series(df["delist_date"])
    else:
        df["delist_date_dt"] = pd.NaT
    df["bucket"] = df.apply(
        lambda r: classify_g2_bucket(
            r["ts_code"], r["name"], r["fund_type"], r["benchmark"]
        ),
        axis=1,
    )
    df["is_canonical"] = df["ts_code"].isin(CANONICAL_CODES)
    return df.dropna(subset=["list_date_dt"])


def load_fund_daily(sector_dir: Path, start: str, end: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    parts: list[pd.DataFrame] = []
    for path in sorted(sector_dir.glob("fund_daily_*.csv")):
        stem_date = path.stem.replace("fund_daily_", "")
        dt = pd.to_datetime(stem_date, format="%Y%m%d", errors="coerce")
        if pd.isna(dt) or dt < start_ts - pd.DateOffset(days=260) or dt > end_ts:
            continue
        try:
            df = pd.read_csv(path, dtype={"ts_code": str})
        except pd.errors.EmptyDataError:
            continue
        if df.empty or "ts_code" not in df.columns:
            continue
        keep = [c for c in ["ts_code", "trade_date", "amount"] if c in df.columns]
        part = df[keep].copy()
        part["trade_date_dt"] = parse_ymd_series(part["trade_date"])
        part = part.dropna(subset=["trade_date_dt"])
        parts.append(part[["ts_code", "trade_date_dt", "amount"]])
    if not parts:
        raise FileNotFoundError(f"No fund_daily_YYYYMMDD.csv files in {sector_dir}")
    daily = pd.concat(parts, ignore_index=True)
    daily["ts_code"] = daily["ts_code"].astype(str)
    daily["amount"] = pd.to_numeric(daily["amount"], errors="coerce").fillna(0.0)
    return daily.sort_values(["ts_code", "trade_date_dt"])


def month_ends_from_daily(daily: pd.DataFrame, start: str, end: str) -> list[pd.Timestamp]:
    cal = pd.DatetimeIndex(sorted(daily["trade_date_dt"].dropna().unique()))
    cal = cal[(cal >= pd.Timestamp(start)) & (cal <= pd.Timestamp(end))]
    if cal.empty:
        return []
    month_ends = pd.Series(cal, index=cal).groupby(cal.to_period("M")).max()
    return [pd.Timestamp(x) for x in month_ends.tolist()]


def compute_month_pool(
    *,
    month_end: pd.Timestamp,
    basic: pd.DataFrame,
    daily: pd.DataFrame,
    min_list_days: int,
    liquidity_days: int,
    min_avg_amount_yuan: float,
    score_mode: str,
    dedup_mode: str,
) -> pd.DataFrame:
    list_age_days = (month_end - basic["list_date_dt"]).dt.days
    active = basic[
        (basic["list_date_dt"] <= month_end)
        & (list_age_days >= min_list_days)
        & (basic["delist_date_dt"].isna() | (basic["delist_date_dt"] > month_end))
    ].copy()
    if active.empty:
        return pd.DataFrame()

    start_window = month_end - pd.DateOffset(days=max(365, liquidity_days * 2))
    d = daily[(daily["trade_date_dt"] <= month_end) & (daily["trade_date_dt"] >= start_window)].copy()
    d = d[d["ts_code"].isin(active["ts_code"])]
    if d.empty:
        return pd.DataFrame()

    liq_rows = []
    for code, g in d.groupby("ts_code", sort=False):
        tail = g.sort_values("trade_date_dt").tail(liquidity_days)
        if len(tail) < max(20, liquidity_days // 3):
            continue
        # Tushare fund_daily.amount is thousand yuan.
        avg_amount_yuan = float(tail["amount"].mean() * 1000.0)
        liq_rows.append((code, avg_amount_yuan, int(len(tail))))
    liq = pd.DataFrame(liq_rows, columns=["ts_code", "avg_amount_yuan", "liquidity_obs"])
    if liq.empty:
        return pd.DataFrame()

    active = active.merge(liq, on="ts_code", how="inner")
    active = active[active["avg_amount_yuan"] >= min_avg_amount_yuan].copy()
    if active.empty:
        return pd.DataFrame()

    active["maturity_days"] = (month_end - active["list_date_dt"]).dt.days
    active["liquidity_rank"] = active["avg_amount_yuan"].rank(pct=True)
    active["maturity_rank"] = active["maturity_days"].rank(pct=True)
    active["canonical_score"] = active["is_canonical"].astype(float)
    if score_mode == "g2_original":
        active["pool_score"] = (
            0.50 * active["canonical_score"]
            + 0.40 * active["liquidity_rank"].fillna(0.0)
            + 0.10
        )
    elif score_mode == "g2_maturity":
        active["pool_score"] = (
            0.50 * active["canonical_score"]
            + 0.40 * active["liquidity_rank"].fillna(0.0)
            + 0.10 * active["maturity_rank"].fillna(0.0)
        )
    elif score_mode == "g2f_maturity":
        active["pool_score"] = (
            0.30 * active["canonical_score"]
            + 0.50 * active["liquidity_rank"].fillna(0.0)
            + 0.20 * active["maturity_rank"].fillna(0.0)
        )
    else:
        raise ValueError(f"Unsupported score_mode: {score_mode}")

    if dedup_mode == "score":
        active = active.sort_values(
            ["benchmark", "pool_score", "avg_amount_yuan", "list_date_dt"],
            ascending=[True, False, False, True],
        )
    elif dedup_mode == "oldest":
        active = active.sort_values(
            ["benchmark", "list_date_dt", "is_canonical", "avg_amount_yuan"],
            ascending=[True, True, False, False],
        )
    else:
        raise ValueError(f"Unsupported dedup_mode: {dedup_mode}")
    active = active.drop_duplicates("benchmark", keep="first").copy()

    selected_parts: list[pd.DataFrame] = []
    for bucket, quota in G2_BUCKET_QUOTAS.items():
        bucket_df = active[active["bucket"].eq(bucket)].copy()
        if bucket_df.empty:
            continue
        bucket_df = bucket_df.sort_values(
            ["pool_score", "is_canonical", "avg_amount_yuan", "list_date_dt"],
            ascending=[False, False, False, True],
        )
        selected_parts.append(bucket_df.head(quota))
    if not selected_parts:
        return pd.DataFrame()
    out = pd.concat(selected_parts, ignore_index=True)
    return out.sort_values(["bucket", "pool_score", "ts_code"], ascending=[True, False, True]).reset_index(drop=True)


def write_outputs(
    *,
    pools: dict[pd.Timestamp, list[str]],
    detail: pd.DataFrame,
    out_pkl: Path,
    report_path: Path,
    detail_path: Path,
    start: str,
    end: str,
    min_list_days: int,
    liquidity_days: int,
    min_avg_amount_yuan: float,
    score_mode: str,
    dedup_mode: str,
) -> None:
    out_pkl.parent.mkdir(parents=True, exist_ok=True)
    with out_pkl.open("wb") as f:
        pickle.dump(pools, f)
    detail.to_csv(detail_path, index=False)

    month_sizes = pd.Series({k: len(v) for k, v in pools.items()}).sort_index()
    bucket_counts = (
        detail.groupby(["month_end", "bucket"]).size().unstack(fill_value=0)
        if not detail.empty
        else pd.DataFrame()
    )
    latest = detail[detail["month_end"].eq(detail["month_end"].max())] if not detail.empty else pd.DataFrame()
    lines = [
        "# G2 PIT Monthly Pool Rebuild",
        "",
        "## Reproduce",
        "",
        "```bash",
        f"python tools/data_prep/build_g2_pit_monthly_pool.py --start {start} --end {end}",
        "```",
        "",
        "## Rules",
        "",
        f"- month end: last available ETF trading day in each month from `{start}` to `{end}`",
        f"- list age: at least `{min_list_days}` calendar days",
        f"- liquidity: trailing `{liquidity_days}` observed trading rows, average `fund_daily.amount * 1000 >= {min_avg_amount_yuan:,.0f}` yuan",
        f"- benchmark de-dup: `{dedup_mode}`",
        "- bucket quotas: " + ", ".join(f"{k}={v}" for k, v in G2_BUCKET_QUOTAS.items()),
        f"- score mode: `{score_mode}`",
        "",
        "## Outputs",
        "",
        f"- pickle: `{out_pkl}`",
        f"- detail: `{detail_path}`",
        f"- report: `{report_path}`",
        "",
        "## Month Size Summary",
        "",
        f"- months: `{len(month_sizes)}`",
        f"- first: `{month_sizes.index.min().date() if len(month_sizes) else ''}`",
        f"- last: `{month_sizes.index.max().date() if len(month_sizes) else ''}`",
        f"- min/median/max size: `{int(month_sizes.min()) if len(month_sizes) else 0}` / `{float(month_sizes.median()):.1f}` / `{int(month_sizes.max()) if len(month_sizes) else 0}`",
        "",
        "## Latest Month",
        "",
        "| bucket | count | ETFs |",
        "|---|---:|---|",
    ]
    if not latest.empty:
        for bucket, g in latest.groupby("bucket"):
            etfs = ", ".join((g["ts_code"] + " " + g["name"]).tolist())
            lines.append(f"| {bucket} | {len(g)} | {etfs} |")
    lines += ["", "## Bucket Counts Tail", ""]
    if not bucket_counts.empty:
        tail = bucket_counts.tail(12).reset_index()
        tail["month_end"] = tail["month_end"].astype(str)
        cols = tail.columns.tolist()
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "|".join(["---"] + ["---:" for _ in cols[1:]]) + "|")
        for _, row in tail.iterrows():
            lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def compare_with_existing(new_pools: dict[pd.Timestamp, list[str]], existing_path: Path) -> pd.DataFrame:
    if not existing_path.exists():
        return pd.DataFrame()
    with existing_path.open("rb") as f:
        old_raw = pickle.load(f)
    old = {pd.Timestamp(k): set(v) for k, v in old_raw.items()}
    rows = []
    for month, new_codes in sorted(new_pools.items()):
        if month not in old:
            continue
        new_set = set(new_codes)
        old_set = old[month]
        inter = len(new_set & old_set)
        union = len(new_set | old_set)
        rows.append({
            "month_end": month.date().isoformat(),
            "old_size": len(old_set),
            "new_size": len(new_set),
            "overlap": inter,
            "jaccard": inter / union if union else np.nan,
            "new_only": ",".join(sorted(new_set - old_set)),
            "old_only": ",".join(sorted(old_set - new_set)),
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild G2 PIT monthly ETF pool from local cache")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--min-list-days", type=int, default=365)
    parser.add_argument("--liquidity-days", type=int, default=180)
    parser.add_argument("--min-avg-amount-yuan", type=float, default=0.0)
    parser.add_argument(
        "--score-mode",
        choices=["g2_original", "g2_maturity", "g2f_maturity"],
        default="g2_original",
        help="G2 historical score variant. g2_original uses +0.10 constant.",
    )
    parser.add_argument(
        "--dedup-mode",
        choices=["score", "oldest"],
        default="score",
        help="Same-benchmark de-dup rule before bucket selection.",
    )
    parser.add_argument("--output-name", default="etf_pool_G2_PIT_monthly_rebuilt_2013.pkl")
    parser.add_argument("--replace-current", action="store_true", help="Also write etf_pool_G2_PIT_monthly.pkl")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    sector_dir = cache_dir / "sector_prosperity"
    basic = load_fund_basic(sector_dir)
    daily = load_fund_daily(sector_dir, args.start, args.end)
    daily = daily[daily["ts_code"].isin(set(basic["ts_code"]))].copy()
    month_ends = month_ends_from_daily(daily, args.start, args.end)
    if not month_ends:
        raise RuntimeError("No month-end dates found in local fund_daily cache")

    pools: dict[pd.Timestamp, list[str]] = {}
    details: list[pd.DataFrame] = []
    for month_end in month_ends:
        selected = compute_month_pool(
            month_end=month_end,
            basic=basic,
            daily=daily,
            min_list_days=args.min_list_days,
            liquidity_days=args.liquidity_days,
            min_avg_amount_yuan=args.min_avg_amount_yuan,
            score_mode=args.score_mode,
            dedup_mode=args.dedup_mode,
        )
        codes = selected["ts_code"].astype(str).tolist() if not selected.empty else []
        pools[pd.Timestamp(month_end)] = codes
        if not selected.empty:
            selected = selected.copy()
            selected.insert(0, "month_end", pd.Timestamp(month_end).date().isoformat())
            details.append(selected[[
                "month_end", "bucket", "ts_code", "name", "benchmark", "fund_type",
                "list_date_dt", "avg_amount_yuan", "liquidity_obs", "maturity_days",
                "is_canonical", "pool_score", "liquidity_rank", "maturity_rank",
            ]])

    detail = pd.concat(details, ignore_index=True) if details else pd.DataFrame()
    out_pkl = sector_dir / args.output_name
    stem = out_pkl.with_suffix("").name
    detail_path = sector_dir / f"{stem}_detail.csv"
    report_path = sector_dir / f"{stem}_report.md"
    write_outputs(
        pools=pools,
        detail=detail,
        out_pkl=out_pkl,
        report_path=report_path,
        detail_path=detail_path,
        start=args.start,
        end=args.end,
        min_list_days=args.min_list_days,
        liquidity_days=args.liquidity_days,
        min_avg_amount_yuan=args.min_avg_amount_yuan,
        score_mode=args.score_mode,
        dedup_mode=args.dedup_mode,
    )

    cmp = compare_with_existing(pools, sector_dir / "etf_pool_G2_PIT_monthly.pkl")
    if not cmp.empty:
        cmp_path = sector_dir / f"{stem}_compare_existing.csv"
        cmp.to_csv(cmp_path, index=False)
        print(f"Compare existing: {cmp_path}")
        print(
            f"Overlap months={len(cmp)}, mean_jaccard={cmp['jaccard'].mean():.3f}, "
            f"median_jaccard={cmp['jaccard'].median():.3f}"
        )

    if args.replace_current:
        current = sector_dir / "etf_pool_G2_PIT_monthly.pkl"
        with current.open("wb") as f:
            pickle.dump(pools, f)
        print(f"Replaced current: {current}")

    sizes = pd.Series({k: len(v) for k, v in pools.items()})
    print(f"Saved: {out_pkl}")
    print(f"Saved: {detail_path}")
    print(f"Saved: {report_path}")
    print(
        f"Months={len(pools)}, first={min(pools).date()}, last={max(pools).date()}, "
        f"size min/median/max={int(sizes.min())}/{sizes.median():.1f}/{int(sizes.max())}"
    )


if __name__ == "__main__":
    main()
