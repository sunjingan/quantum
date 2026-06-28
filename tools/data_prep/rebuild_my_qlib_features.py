"""
从 data/tushare_raw/per_stock 重建 data/my_qlib/features。

Qlib 日频 .bin 格式:
  - 第一个 float: 该股票首个交易日在 calendars/day.txt 里的位置
  - 后续 float: 按交易日历对齐后的字段值

Tushare daily:
  - volume: 成交量，单位为手
  - amount: 成交额，单位为千元
  - vwap = amount * 1000 / (volume * 100) = amount * 10 / volume
"""
from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "tushare_raw" / "per_stock"
QLIB_DIR = BASE_DIR / "data" / "my_qlib"
CALENDAR_PATH = QLIB_DIR / "calendars" / "day.txt"
FIELDS = ["open", "high", "low", "close", "volume", "amount", "pre_close", "vwap"]


def write_feature_bins(csv_path: Path, calendar: list[pd.Timestamp]) -> int:
    symbol = csv_path.stem.lower()
    feature_dir = QLIB_DIR / "features" / symbol
    feature_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"].astype(str))
    df["vwap"] = np.where(df["volume"] > 0, df["amount"] * 10 / df["volume"], np.nan)
    df = df[["date", *FIELDS]].set_index("date").sort_index()

    aligned_calendar = [d for d in calendar if df.index.min() <= d <= df.index.max()]
    aligned = df.reindex(aligned_calendar)
    date_index = calendar.index(aligned.index.min())

    for field in FIELDS:
        out_path = feature_dir / f"{field}.day.bin"
        values = aligned[field].to_numpy(dtype=np.float32)
        np.hstack([date_index, values]).astype("<f").tofile(out_path)

    return 1


def main() -> None:
    calendar = pd.read_csv(CALENDAR_PATH, header=None)[0]
    calendar = pd.to_datetime(calendar).tolist()

    written = 0
    for csv_path in sorted(RAW_DIR.glob("*.csv")):
        written += write_feature_bins(csv_path, calendar)

    print(f"重建 Qlib feature bins: {written} 只股票, {len(FIELDS)} 个字段/只")


if __name__ == "__main__":
    main()
