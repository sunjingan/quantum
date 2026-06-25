# Theme ETF Momentum 实验矩阵与数据缓存记录

实验日期：2026-06-24  
项目目录：`/Users/jingansun/Desktop/codex/quant`  
目的：把用户要求的 A / B / C / R / D 实验清单落成可执行代码，并补一个临时数据预缓存脚本。

## 1. 新增/修改的代码

### 新增文件

- [prefetch_theme_etf_data.py](/Users/jingansun/Desktop/codex/quant/prefetch_theme_etf_data.py)
  - 用于一次性预缓存：
    - ETF 基本信息
    - ETF 日线
    - ETF 份额
    - ETF 指数权重
    - 全 A 财务 statement 缓存
    - daily_basic 快照
    - moneyflow
    - top_inst
- [run_theme_etf_experiments.py](/Users/jingansun/Desktop/codex/quant/run_theme_etf_experiments.py)
  - 批量实验 runner
  - 支持实验标签：
    - `a0` / `a1` / `a2`
    - `b0` / `b1` / `b2` / `b3`
    - `c1` / `c2` / `c3` / `c4` / `c5`
    - `r1` / `r2` / `r3` / `r4`
    - `d0` / `d1` / `d2` / `d3`

### 修改文件

- [strategies/theme_etf_momentum.py](/Users/jingansun/Desktop/codex/quant/strategies/theme_etf_momentum.py)
  - 真实 ETF 日期解析修复
  - `_pivot_wide` / `_latest_snapshot` 修复
  - `RealETFUniverse` / `RealETFStore` 修复

## 2. 这次缓存了什么

### 2.1 股票侧

通过 `prefetch_theme_etf_data.py` 可以缓存：

- `stock_basic_all.csv`
- 每日 `daily_basic`
- 基础财务 statement：
  - `fina_indicator`
  - `income`
  - `cashflow`
  - `balancesheet`

### 2.2 ETF 侧

通过 `prefetch_theme_etf_data.py` 可以缓存：

- `fund_basic`
- `etf_basic`
- `fund_daily`
- `fund_share`
- `index_weight`

### 2.3 富集数据

通过 `prefetch_theme_etf_data.py` 可以缓存：

- `moneyflow`
- `top_inst`

## 3. 实际跑过的 smoke test

回测统一使用：

- 股票数据：`data/a_share_qlib`
- ETF 数据：`data/tushare_cache`
- 关闭 lazy 下载：`QLIB_LAZY_TUSHARE=0`

### A2

命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
python run_theme_etf_experiments.py \
  --market all_a \
  --start 2021-01-01 \
  --end 2021-06-30 \
  --experiments a2 \
  --skip-real-etf
```

结果：

- `total_return = 0.0706`
- `annual_return = 0.3499`
- `annual_vol = 0.8685`
- `max_drawdown = -0.2474`
- `sharpe = 0.4028`

### B0

命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
python run_theme_etf_experiments.py \
  --market all_a \
  --start 2021-01-01 \
  --end 2021-06-30 \
  --experiments b0 \
  --skip-real-etf
```

结果：

- `total_return = 0.0571`
- `annual_return = 0.2769`
- `annual_vol = 0.1775`
- `max_drawdown = -0.0875`
- `sharpe = 1.5597`

### C1

命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
python run_theme_etf_experiments.py \
  --market all_a \
  --start 2021-01-01 \
  --end 2021-06-30 \
  --experiments c1 \
  --skip-real-etf
```

结果：

- `total_return = 0.0085`
- `annual_return = 0.0380`
- `annual_vol = 0.2507`
- `max_drawdown = -0.1131`
- `sharpe = 0.1515`

### D0

命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
python run_theme_etf_experiments.py \
  --market all_a \
  --start 2021-01-01 \
  --end 2021-06-30 \
  --experiments d0
```

结果：

- `total_return = -0.0458`
- `annual_return = -0.1093`
- `annual_vol = 0.2553`
- `max_drawdown = -0.1539`
- `sharpe = -0.4281`

## 4. 复现方法

### 4.1 先缓存数据

```bash
source activate.sh
QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
python prefetch_theme_etf_data.py \
  --start 2018-01-02 \
  --end 2026-06-22 \
  --market all_a
```

如果只想预缓存某一类数据，可以用：

- `--skip-fundamentals`
- `--skip-daily-basic`
- `--skip-moneyflow`
- `--skip-top-inst`
- `--skip-etf`
- `--skip-index-weight`

### 4.2 跑实验矩阵

```bash
source activate.sh
QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
python run_theme_etf_experiments.py \
  --market all_a \
  --start 2018-01-02 \
  --end 2026-06-22
```

默认会跑：

- `a0,a1,a2,b0,b1,b2,b3,c1,c2,c3,c4,c5,r1,r2,r3,r4,d0,d1,d2,d3`

如果只跑某几组，可以用：

```bash
--experiments a0,a1,a2
```

或者：

```bash
--experiments d0,d1,d2,d3
```

## 5. 当前判断

1. 回测引擎本身已经能跑通。
2. A/B/C/D 这几组实验的代码骨架已经建立。
3. 真实 ETF 路径目前在 2021 缓存窗口内可运行，但还不是全历史覆盖。
4. 接下来真正需要做的是补齐全历史 ETF 缓存，再把 D 组拉到更长区间。

