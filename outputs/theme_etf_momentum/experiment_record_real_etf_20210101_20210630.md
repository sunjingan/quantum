# Theme ETF Momentum 真实 ETF 实验记录

实验日期：2026-06-24  
项目目录：`/Users/jingansun/Desktop/codex/quant`  
策略名称：`theme_etf_momentum`  
回测市场：`all_a`  
本轮真实 ETF 实验区间：`2021-01-01` 到 `2021-06-30`  
股票数据源：`data/a_share_qlib`  
ETF 数据源：`data/tushare_cache`

## 1. 任务目标

本轮任务只做一件事：把之前的“行业代理主题层”换成真实 ETF 数据层，并确认真实数据可以驱动完整回测。

策略结构保持不变：

- ETF 层：找强主题
- 成分股层：在强主题里找相对强股票
- 择时层：回踩企稳或平台突破
- 风控层：止损、移动止盈、主题失效、相对强度失效、持仓超期

## 2. 本轮代码改了什么

### 2.1 本轮实际修改文件

`strategies/theme_etf_momentum.py`

本轮修正的内容：

- 新增 `_parse_ymd_series`
  - 统一处理 `20210104`、`20210104.0`、datetime 三种日期格式。
- 修复 `_pivot_wide`
  - 之前它会把已经是 datetime 的 `trade_date` 再按 `%Y%m%d` 解析，结果宽表变空。
  - 现在会先判断 dtype，再选择解析方式。
- 修复 `_latest_snapshot`
  - 同样统一日期解析逻辑，避免快照读取失败。
- 修复 `RealETFUniverse._build_meta`
  - `list_date` 的拼接方式改成显式填充，避免警告和空值处理问题。
- 修复 `RealETFStore`
  - `trade_date` 改成统一解析。
  - `share` 份额宽表同样使用统一解析。
  - `calendar` 不再依赖 `close.index.intersection(amount.index)` 收缩为空，而是直接使用 `close.index` 作为主交易日历。

### 2.2 前置工程代码

下面几个文件是前一轮已经接上的，这次没有再改，但真实 ETF 路径依赖它们：

`strategies/run.py`

- 新增 `--theme-source real_etf | proxy_industry`
- `theme_etf_momentum` 策略入口
- 独立输出目录

`strategies/sector_prosperity.py`

- `prefetch_etf_data(start, end)`
- `fund_basic_etf()`
- `index_weight(index_code, start, end)`
- ETF 相关本地缓存加载

## 3. 真实数据情况

### 3.1 股票数据

使用 `data/a_share_qlib` 中的全 A 股 Qlib 数据。

回测时显式指定：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib
QLIB_LAZY_TUSHARE=0
```

这意味着：

- 股票 OHLCV 从本地 Qlib 读
- 不在回测过程中临时拉股票行情

### 3.2 ETF 数据

使用本地 Tushare 缓存里的真实 ETF 数据。

当前缓存里可用的真实 ETF 日线覆盖：

- 最早：`2021-01-04`
- 最晚：`2021-06-30`

我实际检查过：

- `fund_basic(market='E')` 可用
- `etf_basic()` 可用
- `fund_daily(trade_date=...)` 可用
- `fund_share(trade_date=...)` 可用
- `index_weight()` 可用

但要诚实说明：

- 当前本地缓存中的 ETF 历史还不是 2018-2026 全覆盖。
- 所以本轮“真实 ETF”实验，只能先跑 2021-01-01 到 2021-06-30 这段已有缓存覆盖的窗口。
- 股票层仍然是 `all_a` 全市场。

### 3.3 本轮修复前的实际问题

最开始真实 ETF 路径是空的，原因是日期处理不一致：

- `trade_date` 在缓存里是 `int64`，例如 `20210104`
- 代码先转成 datetime，再丢进 `_pivot_wide`
- `_pivot_wide` 又按 `%Y%m%d` 去解析 datetime 字符串，导致全是 `NaT`

修掉之后，`RealETFStore` 才真正产出非空宽表。

## 4. 验证结果

### 4.1 真实 ETF store 探针

修复后我做了一个直接探针：

- `RealETFUniverse.meta.shape = (1550, 7)`
- `RealETFStore.codes = 405`
- `open.shape = (118, 405)`
- `close.shape = (118, 405)`
- `amount.shape = (118, 405)`
- `share.shape = (118, 404)`
- `calendar` 长度：`118`

说明真实 ETF 宽表已经能正常构建，不再是空表。

### 4.2 单日信号探针

在 `2021-06-18` 做单日探针时：

- `selected_etfs` 非空
- `pool.shape = (30, 21)`
- `scored.shape = (30, 41)`
- `buy_signal` 命中数：`4`
- `buy_signal_a` 命中数：`1`
- `buy_signal_b` 命中数：`3`

说明真实 ETF 层、成分池、择时信号都能串起来。

## 5. 实验定义

本轮跑了四个版本，区间都一样：

- `market = all_a`
- `start = 2021-01-01`
- `end = 2021-06-30`
- `theme_source = real_etf`
- `--no-moneyflow`

四个版本含义：

- `v0`：强 ETF 代理的最简版本
- `v1`：强 ETF + 成分权重版本
- `v2`：强 ETF + 相对强度版本
- `v3`：强 ETF + 相对强度 + 买点过滤版本

## 6. 实验结果

下面表格里的 `targets`、`themes`、`equity` 是输出 CSV 的行数，不是收益指标。

| 版本 | targets 行数 | themes 行数 | equity 行数 | total_return | annual_return | annual_vol | max_drawdown | sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v0 | 142 | 164 | 56 | -0.0527 | -0.2121 | 0.5626 | -0.2492 | -0.3769 |
| v1 | 280 | 164 | 56 | 0.0071 | 0.0317 | 0.4138 | -0.2035 | 0.0767 |
| v2 | 178 | 164 | 56 | 0.1196 | 0.6442 | 0.4997 | -0.1864 | 1.2890 |
| v3 | 7 | 164 | 56 | -0.0470 | -0.1908 | 0.1358 | -0.0672 | -1.4052 |

### 6.1 结果解读

- `v0` 亏损，说明单纯“主题层最简代理”不稳。
- `v1` 基本打平，说明成分权重层没有立刻把策略救起来。
- `v2` 是这轮最好结果，说明“相对强度”这层确实带来主要增益。
- `v3` 结果最差，但回撤也最小，说明买点过滤明显收紧了交易，但过度筛选导致收益被压掉。

## 7. 这轮能得出的结论

### 7.1 已经确认的事实

1. 真实 ETF 数据路径已经打通，不再依赖行业代理。
2. 真实 ETF 宽表能正常构造，日历不再空。
3. ETF 层、成分池层、股票相对强度层、买点层都能串联。
4. 在当前 2021 短窗里，`v2` 的相对强度层最有价值。

### 7.2 暂时不能下的结论

1. 不能据此判断“整个 ETF 动量策略在全历史上有效/无效”。
2. 不能据此判断 2018-2026 全区间的真实 ETF 表现，因为当前 ETF 缓存不覆盖全历史。
3. 不能把这次结果和前一轮行业代理实验直接等价比较，因为数据结构已经变了。

### 7.3 经验判断

- `v2` 说明“强 ETF 中找领涨股”是有信息量的。
- `v3` 说明买点条件目前过硬，信号太少。
- 下一步更合理的方向不是先扫参数，而是补齐更完整的真实 ETF 历史，然后再拆分：
  - 只看 ETF 动量
  - ETF 成分股 top weight
  - ETF 成分股相对强度
  - 相对强度 + 软择时

## 8. 复现方法

### 8.1 运行环境

```bash
source activate.sh
```

### 8.2 复现实验

```bash
QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
python -m strategies.run theme_etf_momentum \
  --market all_a \
  --start 2021-01-01 \
  --end 2021-06-30 \
  --experiment v0 \
  --theme-source real_etf \
  --no-moneyflow
```

把 `--experiment` 改成 `v1`、`v2`、`v3` 即可复现四组实验。

### 8.3 输出目录

每个版本单独输出到：

- `outputs/theme_etf_momentum/v0/`
- `outputs/theme_etf_momentum/v1/`
- `outputs/theme_etf_momentum/v2/`
- `outputs/theme_etf_momentum/v3/`

每个目录里都有：

- `theme_etf_momentum_equity_*.csv`
- `theme_etf_momentum_targets_*.csv`
- `theme_etf_momentum_themes_*.csv`
- `theme_etf_momentum_summary_*.csv`
- `theme_etf_momentum_returns_*.png`

### 8.4 这轮修复后的关键验证命令

如果你只想验证真实 ETF 宽表是否正常，可跑：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
python -c "from pathlib import Path; from strategies.sector_prosperity import SectorProsperityCache; from strategies.theme_etf_momentum import RealETFUniverse, RealETFStore; cache=SectorProsperityCache(Path('config/tushare_token.txt'), Path('data/tushare_cache')); cache.prefetch_etf_data('2021-01-01','2021-06-30'); u=RealETFUniverse(cache); s=RealETFStore(cache,u,'2021-01-01','2021-06-30'); print(u.meta.shape, s.close.shape, len(s.calendar))"
```

## 9. 输出文件

本记录对应的回测输出已经写入：

- `outputs/theme_etf_momentum/v0/`
- `outputs/theme_etf_momentum/v1/`
- `outputs/theme_etf_momentum/v2/`
- `outputs/theme_etf_momentum/v3/`

本记录文件本身：

- `outputs/theme_etf_momentum/experiment_record_real_etf_20210101_20210630.md`

