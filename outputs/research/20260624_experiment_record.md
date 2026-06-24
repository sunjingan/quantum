# Trend-Serenity / SectorProsperity 实验记录

日期：2026-06-24  
范围：`/Users/jingansun/Desktop/codex/quant`

## 1. 这次改了什么

本轮只改了两处业务代码，没有新建策略文件，也没有改 `_risk.py` 本体。

### 修改文件

- `[backtest_v2.py](/Users/jingansun/Desktop/codex/quant/backtest_v2.py)`
  - 接入了 `strategies._risk.RiskParams` 和 `check_single_stop_loss`
  - 新增周频 / 月频切换：`--rebalance-frequency {monthly,weekly}`
  - 新增风控开关：`--risk-controls`
  - 新增最短持有期：`--min-hold-days`
  - 新增单次普通调仓换手上限：`--max-turnover-pct`
  - 让止损 / 移动止盈在每个交易日检查，触发后立即卖出
  - 让普通调仓卖出受最短持有期和换手预算约束
  - 增加了调试字段：`risk_sells`、`risk_sell_notional`、`min_hold_blocks`、`turnover_blocks`

- `[strategies/_utils.py](/Users/jingansun/Desktop/codex/quant/strategies/_utils.py)`
  - 新增 `rebalance_dates(calendar, start, end, frequency)`，支持：
    - `monthly`：每月首个交易日
    - `weekly`：每周首个 `W-FRI` 交易周

### 直接复用但未修改的文件

- `[strategies/_risk.py](/Users/jingansun/Desktop/codex/quant/strategies/_risk.py)`
  - 只被调用，没有改代码
  - 里面已有单票止损 / 移动止盈 / 组合回撤 / 市场状态仓位调节的纯函数

## 2. 本轮实际跑了哪些实验

### 实验 A：编译检查

目的：确认改动后脚本能通过语法编译。  
命令：

```bash
source activate.sh && python -m compileall backtest_v2.py strategies/_risk.py strategies/_utils.py
```

结论：通过。

### 实验 B：周频回测，不加风控

目的：验证新的周频调仓是否可跑，以及在不加止损/持有约束时的真实表现。  
命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib python backtest_v2.py \
  --start 2018-01-02 --end 2026-06-22 \
  --market all_a --target-num 10 \
  --factor-version v2 \
  --sector-model hybrid \
  --rebalance-frequency weekly \
  --skip-enrich
```

实际使用的数据：

- `data/a_share_qlib`
  - `instruments/all_a.txt`
  - `features/**/close.day.bin`
  - `calendars/day.txt`
- `data/tushare_cache`
  - 板块 / 题材图谱缓存
  - 这次没有显式 `--sector-fetch-data`，所以没有在这次实验里额外抓新数据
- 没有使用 enrichment，因为传了 `--skip-enrich`

结果：

- `final_assets = 529,901.975`
- `total_return = -47.01%`
- `max_drawdown = -76.18%`

结论：

- 周频直接把噪音和换手放大了
- 这个策略在周频下明显不稳
- 仅靠题材 / 板块增强不够，必须加风控和持有约束

### 实验 C：周频回测，接入止损 / 移动止盈 + 最短持有 + 换手上限

目的：验证 `_risk.py` 逻辑正式接入主回测后，周频是否能明显改善。  
命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib python backtest_v2.py \
  --start 2018-01-02 --end 2026-06-22 \
  --market all_a --target-num 10 \
  --factor-version v2 \
  --sector-model hybrid \
  --rebalance-frequency weekly \
  --risk-controls \
  --min-hold-days 20 \
  --max-turnover-pct 0.30 \
  --skip-enrich
```

实际使用的数据：

- 同实验 B 的 `data/a_share_qlib`
- 同实验 B 的 `data/tushare_cache`
- 仍然没有 enrichment，因为 `--skip-enrich`

结果：

- `final_assets = 918,593.625`
- `total_return = -8.14%`
- `annual_return = -1.00%`
- `annual_vol = 19.38%`
- `max_drawdown = -55.41%`
- 风控统计：
  - `risk_sells = 76`
  - `risk_sell_notional = 3,119,991.02`
  - `min_hold_blocks = 1,033`
  - `turnover_blocks = 39`

结论：

- 风控和约束显著减轻了周频过度交易
- 结果比“无风控周频”好很多，但仍然没有稳定跑赢基准
- 目前最有效的改善来自“降低抖动”，不是更激进的调仓

## 3. 之前工作区里已有、但这轮没有重跑的对照结果

这些输出已经在工作区里，我在写记录时只把它们当作对照，不当作本轮新实验。

### 月频 / 全 A / V2 基线

- 文件：`outputs/trend_serenity_equity_all_a_v2_buffer_20180102_20260622.csv`
- 结果：`final_assets = 1,024,749.93`，`total_return = 2.47%`
- 数据口径：`data/a_share_qlib` + 本地缓存

### 月频 / 全 A / V2 + Theme

- 文件：`outputs/trend_serenity_equity_all_a_v2_theme_buffer_20180102_20260622.csv`
- 结果：`final_assets = 2,590,586.669`，`total_return = 159.06%`
- 数据口径：`data/a_share_qlib` + 本地缓存

### 月频 / 全 A / V2 + Sector Hybrid

- 文件：`outputs/trend_serenity_equity_all_a_v2_sector-hybrid_buffer_20180102_20260622.csv`
- 结果：`final_assets = 1,281,633.177`，`total_return = 28.16%`
- 数据口径：`data/a_share_qlib` + 本地缓存

### 月频 / 全 A / V2 + Sector Hybrid + Topic Graph

- 文件：`outputs/trend_serenity_equity_all_a_v2_sector-hybrid-topic_buffer_20180102_20260622.csv`
- 结果：`final_assets = 1,281,633.177`，`total_return = 28.16%`
- 说明：这个输出和上一个在当前工作区里数值一致

### 月频 / 全 A / V1 旧版对照

- 文件：`outputs/trend_serenity_equity_all_a_v1_nobuffer_20180102_20260622.csv`
- 结果：`final_assets = 1,602,278.908`，`total_return = 60.23%`
- 数据口径：`data/a_share_qlib` + 本地缓存

### 月频 / HS300 / V2 对照

- 文件：`outputs/trend_serenity_equity_hs300_v2_buffer_20180102_20260622.csv`
- 结果：`final_assets = 1,269,626.05`，`total_return = 26.96%`

## 4. 我从这些实验里得到的结论

1. 这个策略更像中周期策略，不适合直接用高频周调仓硬推。
2. `_risk.py` 里的止损 / 移动止盈值得保留，接入主流程后能明显降低周频的尾部风险。
3. 最短持有期和换手上限是必要的，否则周频会被目标池切换拖着跑。
4. 仅靠主题 / 板块热度增强，不能自动解决收益和回撤问题；它更像筛选器，不是完整的风险控制。

## 5. 别人如何复现

### 环境前提

- 仓库根目录是 `/Users/jingansun/Desktop/codex/quant`
- 已有本地 Qlib 数据：`data/a_share_qlib`
- 已有本地 Tushare 缓存：`data/tushare_cache`
- 先执行：

```bash
source activate.sh
```

### 复现本轮周频风险实验

```bash
QLIB_PROVIDER_URI=data/a_share_qlib python backtest_v2.py \
  --start 2018-01-02 --end 2026-06-22 \
  --market all_a --target-num 10 \
  --factor-version v2 \
  --sector-model hybrid \
  --rebalance-frequency weekly \
  --risk-controls \
  --min-hold-days 20 \
  --max-turnover-pct 0.30 \
  --skip-enrich
```

### 复现月频对照

把 `--rebalance-frequency weekly` 改成 `monthly`，并按需要去掉 `--risk-controls` 即可。

### 输出位置

- 净值：`outputs/trend_serenity_equity_*.csv`
- 持仓：`outputs/trend_serenity_targets_*.csv`
- 图表：`outputs/trend_serenity_returns_*.png`

### 说明

- 我这次没有在实验里额外抓取线上新数据，全部依赖本地已有缓存和 `data/a_share_qlib`
- `--skip-enrich` 的实验不使用 enrichment，因此不涉及那部分缓存

## 6. 工作区里已有的 `trend-serenity` 全 A 实验

这部分是把当前工作区 `outputs/` 里已经存在的 `trend_serenity` 全 A 输出，按可复现口径整理出来。  
说明分两类：

- `已确认复现`：我能从当前 `backtest_v2.py` 和已有输出文件直接对上参数
- `文件名推断`：工作区里只有输出文件，没有保存对应 shell 命令，所以这里只能按文件名和当前脚本逻辑推断

### 6.1 已确认复现的全 A 实验

统一前提：

```bash
source activate.sh
QLIB_PROVIDER_URI=data/a_share_qlib
```

#### 全 A / V2 / buffer

命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib python backtest_v2.py \
  --start 2018-01-02 --end 2026-06-22 \
  --market all_a \
  --factor-version v2
```

对应输出：

- `[outputs/trend_serenity_equity_all_a_v2_buffer_20180102_20260622.csv](/Users/jingansun/Desktop/codex/quant/outputs/trend_serenity_equity_all_a_v2_buffer_20180102_20260622.csv)`

结果：

- `final_assets = 1,024,749.93`
- `total_return = 2.47%`

#### 全 A / V2 / nobuffer

命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib python backtest_v2.py \
  --start 2018-01-02 --end 2026-06-22 \
  --market all_a \
  --factor-version v2 \
  --no-buffer
```

对应输出：

- `[outputs/trend_serenity_equity_all_a_v2_nobuffer_20180102_20260622.csv](/Users/jingansun/Desktop/codex/quant/outputs/trend_serenity_equity_all_a_v2_nobuffer_20180102_20260622.csv)`

#### 全 A / V2 / theme

命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib python backtest_v2.py \
  --start 2018-01-02 --end 2026-06-22 \
  --market all_a \
  --factor-version v2 \
  --v2-experiment theme
```

对应输出：

- `[outputs/trend_serenity_equity_all_a_v2_theme_buffer_20180102_20260622.csv](/Users/jingansun/Desktop/codex/quant/outputs/trend_serenity_equity_all_a_v2_theme_buffer_20180102_20260622.csv)`

结果：

- `final_assets = 2,590,586.669`
- `total_return = 159.06%`

#### 全 A / V2 / sector-hybrid

命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib python backtest_v2.py \
  --start 2018-01-02 --end 2026-06-22 \
  --market all_a \
  --factor-version v2 \
  --sector-model hybrid
```

对应输出：

- `[outputs/trend_serenity_equity_all_a_v2_sector-hybrid_buffer_20180102_20260622.csv](/Users/jingansun/Desktop/codex/quant/outputs/trend_serenity_equity_all_a_v2_sector-hybrid_buffer_20180102_20260622.csv)`

结果：

- `final_assets = 1,281,633.177`
- `total_return = 28.16%`

#### 全 A / V2 / sector-hybrid-topic

当前工作区里该输出文件和 `sector-hybrid_buffer` 数值一致。  
这表示在当时的脚本状态下，`topic graph` 的增益没有再把结果拉开，至少从这份输出看是这样。

对应输出：

- `[outputs/trend_serenity_equity_all_a_v2_sector-hybrid-topic_buffer_20180102_20260622.csv](/Users/jingansun/Desktop/codex/quant/outputs/trend_serenity_equity_all_a_v2_sector-hybrid-topic_buffer_20180102_20260622.csv)`

结果：

- `final_assets = 1,281,633.177`
- `total_return = 28.16%`

#### 全 A / V1 / nobuffer

命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib python backtest_v2.py \
  --start 2018-01-02 --end 2026-06-22 \
  --market all_a \
  --factor-version v1 \
  --no-buffer
```

对应输出：

- `[outputs/trend_serenity_equity_all_a_v1_nobuffer_20180102_20260622.csv](/Users/jingansun/Desktop/codex/quant/outputs/trend_serenity_equity_all_a_v1_nobuffer_20180102_20260622.csv)`

结果：

- `final_assets = 1,602,278.908`
- `total_return = 60.23%`

### 6.2 周频相关的全 A 实验

#### 全 A / V2 / sector-hybrid-topic / weekly

命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib python backtest_v2.py \
  --start 2018-01-02 --end 2026-06-22 \
  --market all_a \
  --factor-version v2 \
  --sector-model hybrid \
  --rebalance-frequency weekly
```

对应输出：

- `[outputs/trend_serenity_equity_all_a_v2_sector-hybrid-topic_buffer_weekly_20180102_20260622.csv](/Users/jingansun/Desktop/codex/quant/outputs/trend_serenity_equity_all_a_v2_sector-hybrid-topic_buffer_weekly_20180102_20260622.csv)`

结果：

- `final_assets = 529,901.975`
- `total_return = -47.01%`

#### 全 A / V2 / sector-hybrid-topic / weekly / 风控版

命令：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib python backtest_v2.py \
  --start 2018-01-02 --end 2026-06-22 \
  --market all_a \
  --factor-version v2 \
  --sector-model hybrid \
  --rebalance-frequency weekly \
  --risk-controls \
  --min-hold-days 20 \
  --max-turnover-pct 0.30 \
  --skip-enrich
```

对应输出：

- `[outputs/trend_serenity_equity_all_a_v2_sector-hybrid-topic_buffer_weekly_risk-hold20-turn30_20180102_20260622.csv](/Users/jingansun/Desktop/codex/quant/outputs/trend_serenity_equity_all_a_v2_sector-hybrid-topic_buffer_weekly_risk-hold20-turn30_20180102_20260622.csv)`

结果：

- `final_assets = 918,593.625`
- `total_return = -8.14%`
- `max_drawdown = -55.41%`

### 6.3 文件名推断、但未重新跑过的输出

下面这些文件在 `outputs/` 里存在，但当前工作区没有保留下来对应命令，所以这里只能按文件名做推断，不当作本轮新实验。

- `[outputs/trend_serenity_equity_all_a_20000104_20260622.csv](/Users/jingansun/Desktop/codex/quant/outputs/trend_serenity_equity_all_a_20000104_20260622.csv)`
- `[outputs/trend_serenity_equity_all_a_20160622_20260622.csv](/Users/jingansun/Desktop/codex/quant/outputs/trend_serenity_equity_all_a_20160622_20260622.csv)`

推断口径：

- 这两份大概率也是 `trend_serenity` 的全 A 长区间回测
- 起始日不同，其他逻辑大体应当和当前 `backtest_v2.py` 同源
- 但没有可核验命令，因此不建议把它们当作已完全复现的实验记录
