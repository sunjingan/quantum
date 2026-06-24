"""
Download recent 10-year A-share daily data from Tushare and build Qlib bins.

Default output:
  raw daily partitions: data/tushare_raw/a_share_daily_10y/YYYYMMDD.csv
  qlib binary cache:    data/a_share_qlib

Usage:
  source activate.sh
  python download_a_share_10y.py

Resume:
  Re-run the same command. Existing non-empty daily CSV partitions are skipped.
"""
from __future__ import annotations

import argparse
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import tushare as ts


BASE_DIR = Path(__file__).resolve().parent
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
RAW_DIR = BASE_DIR / "data" / "tushare_raw" / "a_share_daily_10y"
META_DIR = BASE_DIR / "data" / "tushare_raw" / "a_share_meta_10y"
QLIB_DIR = BASE_DIR / "data" / "a_share_qlib"

FIELDS = ["open", "high", "low", "close", "pre_close", "volume", "amount", "vwap", "factor"]
THREAD_LOCAL = threading.local()
REQUEST_LOCK = threading.Lock()
COOLDOWN_LOCK = threading.Lock()
LAST_REQUEST_AT = 0.0
COOLDOWN_UNTIL = 0.0


def qlib_code(ts_code: str) -> str:
    symbol, exchange = ts_code.split(".")
    return f"{exchange.lower()}{symbol}".lower()


def ymd(date: str | pd.Timestamp) -> str:
    return pd.Timestamp(date).strftime("%Y%m%d")


def get_pro():
    return ts.pro_api(token=TOKEN_PATH.read_text().strip())


def get_thread_pro():
    if not hasattr(THREAD_LOCAL, "pro"):
        THREAD_LOCAL.pro = get_pro()
    return THREAD_LOCAL.pro


def acquire_request_slot(min_interval: float) -> None:
    if min_interval <= 0:
        return
    global LAST_REQUEST_AT
    while True:
        with REQUEST_LOCK:
            now = time.monotonic()
            wait = LAST_REQUEST_AT + min_interval - now
            if wait <= 0:
                LAST_REQUEST_AT = now
                return
        time.sleep(wait)


def wait_for_cooldown() -> None:
    global COOLDOWN_UNTIL
    while True:
        with COOLDOWN_LOCK:
            now = time.monotonic()
            wait = COOLDOWN_UNTIL - now
            if wait <= 0:
                return
        time.sleep(wait)


def set_cooldown(seconds: float) -> None:
    global COOLDOWN_UNTIL
    with COOLDOWN_LOCK:
        COOLDOWN_UNTIL = max(COOLDOWN_UNTIL, time.monotonic() + seconds)


def fetch_stock_basic(pro) -> pd.DataFrame:
    META_DIR.mkdir(parents=True, exist_ok=True)
    out_path = META_DIR / "stock_basic_LD.csv"
    parts = []
    for status in ["L", "D"]:
        df = pro.stock_basic(
            exchange="",
            list_status=status,
            fields="ts_code,symbol,name,area,industry,list_date,delist_date",
        )
        if df is not None and not df.empty:
            df["list_status"] = status
            parts.append(df)
    result = pd.concat(parts, ignore_index=True)
    result["qlib_code"] = result["ts_code"].map(qlib_code)
    result.to_csv(out_path, index=False)
    return result


def fetch_calendar(pro, start: str, end: str) -> list[str]:
    META_DIR.mkdir(parents=True, exist_ok=True)
    out_path = META_DIR / f"trade_cal_{ymd(start)}_{ymd(end)}.csv"
    if out_path.exists():
        df = pd.read_csv(out_path, dtype={"cal_date": str})
    else:
        df = pro.trade_cal(
            exchange="SSE",
            start_date=ymd(start),
            end_date=ymd(end),
            is_open="1",
            fields="cal_date",
        )
        df.to_csv(out_path, index=False)
    return sorted(df["cal_date"].astype(str).tolist())


def download_one_partition(trade_date: str, request_gap: float, retry: int) -> tuple[str, bool]:
    out_path = RAW_DIR / f"{trade_date}.csv"
    if out_path.exists() and out_path.stat().st_size > 40:
        return trade_date, True

    pro = get_thread_pro()
    last_err = None
    fields = "ts_code,trade_date,open,high,low,close,pre_close,vol,amount"
    for attempt in range(1, retry + 1):
        try:
            wait_for_cooldown()
            acquire_request_slot(request_gap)
            df = pro.daily(trade_date=trade_date, fields=fields)
            if df is None:
                df = pd.DataFrame(columns=fields.split(","))
            df.to_csv(out_path, index=False)
            return trade_date, False
        except Exception as exc:
            last_err = exc
            msg = str(exc)
            if "频率超限" in msg or "frequency" in msg.lower():
                set_cooldown(120.0)
            wait = max(10.0, request_gap * (2 ** (attempt - 1)) + 3)
            print(f"{trade_date} download failed attempt {attempt}/{retry}: {exc}; sleep {wait:.1f}s")
            time.sleep(wait)
    raise RuntimeError(f"Failed to download {trade_date}: {last_err}") from last_err


def download_daily_partitions(pro, dates: list[str], request_gap: float, retry: int, workers: int) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    done = sum(1 for trade_date in dates if (RAW_DIR / f"{trade_date}.csv").exists() and (RAW_DIR / f"{trade_date}.csv").stat().st_size > 40)
    missing_dates = [trade_date for trade_date in dates if not ((RAW_DIR / f"{trade_date}.csv").exists() and (RAW_DIR / f"{trade_date}.csv").stat().st_size > 40)]
    if not missing_dates:
        print(f"download progress: {done}/{len(dates)} daily partitions")
        return

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(download_one_partition, trade_date, request_gap, retry): trade_date for trade_date in missing_dates}
        for i, future in enumerate(as_completed(futures), start=1):
            trade_date, existed = future.result()
            if not existed:
                done += 1
            if done % 20 == 0 or done == len(dates) or i == len(missing_dates):
                print(f"download progress: {done}/{len(dates)} daily partitions")


def normalize_partition(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"ts_code": str, "trade_date": str})
    if df.empty:
        return df
    df = df.rename(columns={"vol": "volume"})
    df["code"] = df["ts_code"].map(qlib_code)
    df["vwap"] = np.where(df["volume"] > 0, df["amount"] * 10 / df["volume"], np.nan)
    df["factor"] = 1.0
    return df[["code", *FIELDS]]


def write_instruments(codes: list[str], first_idx: np.ndarray, last_idx: np.ndarray, dates: list[str]) -> None:
    inst_dir = QLIB_DIR / "instruments"
    inst_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for code, start_i, end_i in zip(codes, first_idx, last_idx):
        if start_i < 0 or end_i < 0:
            continue
        rows.append((code, pd.Timestamp(dates[int(start_i)]).strftime("%Y-%m-%d"), pd.Timestamp(dates[int(end_i)]).strftime("%Y-%m-%d")))
    out = pd.DataFrame(rows, columns=["code", "start", "end"]).sort_values("code")
    for name in ["all.txt", "all_a.txt"]:
        out.to_csv(inst_dir / name, sep="\t", header=False, index=False)
    print(f"instruments: {len(out)} stocks -> {inst_dir}")


def build_qlib_bins(dates: list[str]) -> None:
    files = [RAW_DIR / f"{d}.csv" for d in dates if (RAW_DIR / f"{d}.csv").exists()]
    if not files:
        raise RuntimeError(f"No daily CSV partitions found in {RAW_DIR}")

    print("scan symbols from daily partitions...")
    code_set = set()
    for i, path in enumerate(files, start=1):
        df = pd.read_csv(path, usecols=["ts_code"], dtype={"ts_code": str})
        if not df.empty:
            code_set.update(df["ts_code"].map(qlib_code).tolist())
        if i % 250 == 0:
            print(f"scan progress: {i}/{len(files)}")
    codes = sorted(code_set)
    code_to_idx = {code: i for i, code in enumerate(codes)}
    n_days, n_codes = len(dates), len(codes)
    print(f"building matrices: {n_days} days x {n_codes} stocks x {len(FIELDS)} fields")

    matrices = {field: np.full((n_days, n_codes), np.nan, dtype=np.float32) for field in FIELDS}

    for day_idx, date in enumerate(dates):
        path = RAW_DIR / f"{date}.csv"
        if not path.exists():
            continue
        df = normalize_partition(path)
        if df.empty:
            continue
        idx = df["code"].map(code_to_idx).to_numpy()
        for field in FIELDS:
            matrices[field][day_idx, idx] = pd.to_numeric(df[field], errors="coerce").to_numpy(dtype=np.float32)
        if (day_idx + 1) % 250 == 0 or day_idx + 1 == n_days:
            print(f"matrix fill progress: {day_idx + 1}/{n_days}")

    cal_dir = QLIB_DIR / "calendars"
    cal_dir.mkdir(parents=True, exist_ok=True)
    calendar_text = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in dates]
    np.savetxt(cal_dir / "day.txt", calendar_text, fmt="%s", encoding="utf-8")

    close = matrices["close"]
    valid = ~np.isnan(close)
    any_valid = valid.any(axis=0)
    first_idx = np.where(any_valid, valid.argmax(axis=0), -1)
    last_idx = np.where(any_valid, n_days - 1 - np.flip(valid, axis=0).argmax(axis=0), -1)

    features_dir = QLIB_DIR / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    for code_idx, code in enumerate(codes):
        if first_idx[code_idx] < 0:
            continue
        start_i = int(first_idx[code_idx])
        end_i = int(last_idx[code_idx])
        code_dir = features_dir / code
        code_dir.mkdir(parents=True, exist_ok=True)
        for field in FIELDS:
            values = matrices[field][start_i : end_i + 1, code_idx]
            np.hstack([start_i, values]).astype("<f").tofile(code_dir / f"{field}.day.bin")
        if (code_idx + 1) % 500 == 0 or code_idx + 1 == len(codes):
            print(f"bin write progress: {code_idx + 1}/{len(codes)}")

    write_instruments(codes, first_idx, last_idx, dates)
    print(f"Qlib data built: {QLIB_DIR}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2016-06-22", help="inclusive start date")
    parser.add_argument("--end", default="2026-06-22", help="inclusive end date")
    parser.add_argument("--mode", choices=["all", "download", "build"], default="all")
    parser.add_argument("--sleep", type=float, default=0.0, help="legacy per-call sleep after success; usually keep 0 with workers")
    parser.add_argument("--retry", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2, help="parallel download workers for daily partitions")
    parser.add_argument("--request-gap", type=float, default=1.5, help="minimum seconds between Tushare requests across workers")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pro = get_pro()
    stock_basic = fetch_stock_basic(pro)
    dates = fetch_calendar(pro, args.start, args.end)
    print(f"A-share stock_basic: {len(stock_basic)} listed/delisted records")
    print(f"trade calendar: {dates[0]} -> {dates[-1]}, {len(dates)} open days")
    print(f"raw dir: {RAW_DIR}")
    print(f"qlib dir: {QLIB_DIR}")

    if args.mode in {"all", "download"}:
        download_daily_partitions(pro, dates, args.request_gap, args.retry, args.workers)
    if args.mode in {"all", "build"}:
        build_qlib_bins(dates)


if __name__ == "__main__":
    main()
