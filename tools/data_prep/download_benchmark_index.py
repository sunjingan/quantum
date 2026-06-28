"""
下载沪深 300 指数日线，并写成 Qlib benchmark 可读取的二进制格式。

用法:
  source activate.sh
  python tools/data_prep/download_benchmark_index.py
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import tushare as ts


BASE_DIR = Path(__file__).resolve().parent
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
RAW_DIR = BASE_DIR / "data" / "tushare_raw" / "index"

INDEX_TS_CODE = "000300.SH"
INDEX_QLIB_CODE = "sh000300"
START_DATE = "20200101"
END_DATE = "20250620"
FIELDS = ["open", "high", "low", "close", "volume", "amount", "pre_close", "vwap"]


def load_token() -> str:
    return TOKEN_PATH.read_text().strip()


def download_index_daily(start_date: str, end_date: str) -> pd.DataFrame:
    pro = ts.pro_api(token=load_token())
    df = pro.index_daily(
        ts_code=INDEX_TS_CODE,
        start_date=start_date,
        end_date=end_date,
        fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount",
    )
    if df is None or df.empty:
        raise RuntimeError(f"没有拉到指数行情: {INDEX_TS_CODE}")

    df = df.rename(columns={"trade_date": "date", "vol": "volume"})
    df["date"] = pd.to_datetime(df["date"].astype(str))
    df = df.sort_values("date")
    df["vwap"] = np.where(df["volume"] > 0, df["amount"] * 10 / df["volume"], np.nan)
    return df[["date", *FIELDS]]


def write_raw_csv(df: pd.DataFrame) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / "SH000300.csv"
    df.to_csv(out_path, index=False)
    return out_path


def write_qlib_bins(df: pd.DataFrame, qlib_dir: Path) -> int:
    calendar = pd.read_csv(qlib_dir / "calendars" / "day.txt", header=None)[0]
    calendar = pd.to_datetime(calendar).tolist()

    feature_dir = qlib_dir / "features" / INDEX_QLIB_CODE
    feature_dir.mkdir(parents=True, exist_ok=True)

    indexed = df.set_index("date").sort_index()
    aligned_calendar = [d for d in calendar if indexed.index.min() <= d <= indexed.index.max()]
    aligned = indexed.reindex(aligned_calendar)
    date_index = calendar.index(aligned.index.min())

    for field in FIELDS:
        values = aligned[field].to_numpy(dtype=np.float32)
        np.hstack([date_index, values]).astype("<f").tofile(feature_dir / f"{field}.day.bin")

    return len(aligned)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=START_DATE)
    parser.add_argument("--end", default=END_DATE)
    parser.add_argument("--qlib-dir", default=str(BASE_DIR / "data" / "my_qlib"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    qlib_dir = Path(args.qlib_dir)
    df = download_index_daily(args.start, args.end)
    raw_path = write_raw_csv(df)
    rows = write_qlib_bins(df, qlib_dir)
    print(f"指数原始数据: {raw_path}")
    print(f"写入 Qlib benchmark: {INDEX_QLIB_CODE}, {rows} 行")


if __name__ == "__main__":
    main()
