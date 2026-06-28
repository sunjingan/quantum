# ETF Loop 数据准备脚本

这里放的是 ETF Loop 相关的数据下载和预热脚本。

常用入口：

- `download_benchmarks.py`
- `download_a_share_10y.py`
- `download_tushare.py`
- `download_benchmark_index.py`
- `prefetch_enrichment.py`
- `prefetch_theme_etf_data.py`
- `prefetch_fundamental.py`
- `rebuild_my_qlib_features.py`

通常先执行：

```bash
source activate.sh
python tools/data_prep/download_benchmarks.py
```

然后再跑主线回测和分析脚本。
