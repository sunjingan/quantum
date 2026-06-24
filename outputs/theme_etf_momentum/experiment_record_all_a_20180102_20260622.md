# Theme ETF Momentum 全量 A 股实验记录

实验日期：2026-06-24  
项目目录：`/Users/jingansun/Desktop/codex/quant`  
策略名称：`theme_etf_momentum`  
回测区间：`2018-01-02` 到 `2026-06-22`  
回测市场：全量 A 股，`--market all_a`  
数据源：`data/a_share_qlib`

## 1. 本次做了什么

本次新增并实验了一套“主题动量 + 成分股相对强度 + 技术择时”策略。策略意图来自用户给出的规则：

- ETF/theme 层：找成交活跃、趋势向上、资金/成交活跃度改善的强主题。
- 成分股层：在强主题里找持续跑赢主题的股票。
- 择时层：只在回踩企稳或平台突破时买入。
- 风控层：跌破趋势、相对强度失效、主题失效、固定止损、移动止盈、持仓超期未创新高时卖出。

需要诚实说明：本次实验没有使用真实 ETF 持仓、ETF 份额、ETF 日线或 ETF 跟踪指数成分。当前本地缓存中没有完整的这些历史数据。因此代码中第一版实际采用的是“行业主题代理 ETF”的方式：用 `stock_basic.industry` 把股票分组，把每个行业组当作一个主题/ETF 代理来打分和构建成分股池。

## 2. 改了/创建了哪些代码

### 2.1 新增文件

`strategies/theme_etf_momentum.py`

主要内容：

- `ThemeETFParams`
  - 策略参数，包括主题数量、成分股数量、相对强度阈值、买点、止损、移动止盈、实验版本等。
- `DailyFrames`
  - 从 Qlib feature bin 中读取 `open/high/low/close/volume/amount`。
- `RollingFeatureStore`
  - 后来新增的优化类。一次性预计算全市场滚动指标：
    - `ma20`, `ma60`
    - `ret20`, `ret60`
    - `amount20`, `amount60`, `amount5`
    - `vol20`
    - `high20`, `high60`, `high10_prev`, `low10`
    - `volume_ma5`, `volume_ma20`
    - `pct_chg`
  - 目的是避免每天用 `close.loc[:date, codes].tail(...)` 对全市场反复切片。
- `ThemeUniverse`
  - 从 `stock_basic` 构建 `code -> industry/name/list_date`，并缓存 `theme -> codes`。
- `DailyBasicStore`
  - 一次性索引已有 `daily_basic` 缓存文件，每个回测日取“当时可见的最近一份”。
  - 避免每日扫描目录。
- `MoneyFlowCache`
  - 可选资金流/龙虎榜增强，但本次全量 A 股实验全部使用 `--no-moneyflow`，所以没有启用。
- `compute_theme_scores_fast`
  - 快速计算主题层打分。
- `build_candidate_pool_fast`
  - 快速构建强主题成分股池。
- `score_stock_pool_fast`
  - 快速计算个股相对强度、结构分、最终分。
- `add_buy_signals_fast`
  - 快速计算买点 A/B。
- `sell_reasons_fast`
  - 快速计算卖出原因。
- `run_theme_etf_backtest`
  - 策略主回测循环。
- `output_paths`
  - 固定输出到独立目录：`outputs/theme_etf_momentum/<v0|v1|v2|v3>/`。

### 2.2 修改文件

`strategies/run.py`

- 新增 CLI 策略入口：
  - `theme_etf_momentum`
- 新增参数：
  - `--experiment {v0,v1,v2,v3}`
  - `--target-num`
  - `--etf-count`
  - `--no-moneyflow`
  - `--no-market-filter`
- 新策略输出文件：
  - equity CSV
  - targets CSV
  - themes CSV
  - summary CSV
  - returns PNG

`strategies/__init__.py`

- 导出：
  - `ThemeETFParams`
  - `compute_theme_scores`
  - `select_themes`
  - `select_theme_etf_targets`
  - `run_theme_etf_backtest`

### 2.3 过程中修过的问题

1. `pct_change` 警告
   - 原来 `pct_change()` 使用 pandas 默认填充行为，长回测会刷 FutureWarning。
   - 改为 `pct_change(fill_method=None)`。

2. 候选池为空时报错
   - 全量 A 股长回测中，某些日期 `stock_scores` 为空，但卖出检查仍访问 `stock_scores["code"]`。
   - 加了空 DataFrame 防护。

3. V3 买点过严
   - 初版错误地要求“买点 A/B 都必须叠加 pullback_zone”。
   - 修正为：
     - 买点 A：放量回踩企稳，需要满足 pullback_zone。
     - 买点 B：平台突破，独立成立即可。

4. 全量 A 股性能问题
   - 初版每天反复对全市场做 `loc[:date].tail(...)`，V0 长回测跑得非常慢。
   - 参考 `trend_serenity_v2.py` 的思路，改成批量/缓存式处理：
     - 一次性加载矩阵；
     - 一次性预计算 rolling features；
     - 日循环只读取当日一行；
     - 持仓检查只遍历当前持仓，不遍历全市场股票。

## 3. 实际使用的数据

### 3.1 价格行情数据

使用：

```text
data/a_share_qlib
```

命令中明确指定：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib
QLIB_LAZY_TUSHARE=0
```

说明：

- `activate.sh` 启动时会打印默认 Qlib 数据为 `data/my_qlib`，但本次命令用环境变量覆盖为 `data/a_share_qlib`。
- `QLIB_LAZY_TUSHARE=0` 表示不临时下载/补齐数据，保证实验只使用本地已有数据。

使用字段：

- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`

使用基准：

- `sh000300`

本地 calendar：

- 起始：`2000-01-04`
- 结束：`2026-06-22`

本次回测实际区间：

- `2018-01-02` 到 `2026-06-22`

### 3.2 股票池数据

使用 universe 文件：

```text
data/a_share_qlib/instruments/all_a.txt
```

文件行数：

```text
5856
```

这不是说每天都有 5856 只股票可交易，而是本地全量 A 股 instrument 文件包含 5856 行。每日是否有价格数据由 Qlib feature 和 NaN 决定。

### 3.3 股票基础信息

使用已有缓存中的 `stock_basic_all.csv`。本次没有新抓取。

可用缓存：

```text
data/tushare_cache/trend_serenity/stock_basic_all.csv
data/tushare_cache/poe_pb_roe/stock_basic_all.csv
data/tushare_cache/poe_pb_roe/trend_serenity/stock_basic_all.csv
```

代码优先读取：

```text
data/tushare_cache/trend_serenity/stock_basic_all.csv
```

用途：

- 股票名称过滤 ST/退市风险字样。
- 上市天数过滤。
- 行业主题分组。

### 3.4 daily_basic 数据

使用已有缓存中的最近可见 `daily_basic` 文件，不逐日新抓。

候选目录：

```text
data/tushare_cache/theme_etf_momentum/daily_basic
data/tushare_cache/trend_serenity/daily_basic
data/tushare_cache/poe_pb_roe/daily_basic
```

本次策略代码逻辑：

- 对每个回测日，取 `<= data_date` 的最近一个缓存文件。
- 如果没有缓存，则市值/换手过滤自动退化。

诚实说明：这不是完整逐日 daily_basic 数据。部分日期使用的是最近一次已有缓存快照，因此 `turnover_rate`、`total_mv` 等过滤可能不是严格逐日点时数据。

### 3.5 没有使用的数据

本次全量 A 股四个实验都使用了：

```bash
--no-moneyflow
```

因此没有使用：

- `moneyflow`
- `top_inst`
- 龙虎榜机构净买入

也没有使用真实 ETF 数据：

- 未使用 ETF 日线。
- 未使用 ETF 份额。
- 未使用 ETF 持仓。
- 未使用 ETF 跟踪指数成分。

当前“ETF 层”实际是行业主题代理层。

## 4. 实验版本定义

所有版本公共参数：

| 参数 | 值 |
|---|---:|
| 回测区间 | `2018-01-02` 到 `2026-06-22` |
| 市场 | `all_a` |
| 初始资金 | `500000` |
| 主题数量 | `5` |
| 最大持仓数 | `5` |
| 单主题最大权重 | `40%` |
| `rs_top_pct` | `0.2` |
| 固定止损 | `-8%` |
| 移动止盈 | `-10%` |
| 资金流增强 | 关闭 |
| lazy 下载 | 关闭 |

版本含义：

| 版本 | 含义 | 检验问题 |
|---|---|---|
| V0 | 只买强主题代理，每个主题取一个代表股票 | 主题轮动本身是否有效 |
| V1 | 强主题内买流动性/市值靠前成分股 | 成分股池是否有用 |
| V2 | V1 + 个股相对主题强度 | 领涨股是否有 alpha |
| V3 | V2 + 回踩/突破买点 + 卖出纪律 | 技术择时是否改善收益回撤 |

## 5. 实验命令

运行前：

```bash
cd /Users/jingansun/Desktop/codex/quant
source activate.sh
```

V0：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
python -m strategies.run theme_etf_momentum \
  --market all_a \
  --start 2018-01-02 \
  --end 2026-06-22 \
  --experiment v0 \
  --no-moneyflow
```

V1：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
python -m strategies.run theme_etf_momentum \
  --market all_a \
  --start 2018-01-02 \
  --end 2026-06-22 \
  --experiment v1 \
  --no-moneyflow
```

V2：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
python -m strategies.run theme_etf_momentum \
  --market all_a \
  --start 2018-01-02 \
  --end 2026-06-22 \
  --experiment v2 \
  --no-moneyflow
```

V3：

```bash
QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
python -m strategies.run theme_etf_momentum \
  --market all_a \
  --start 2018-01-02 \
  --end 2026-06-22 \
  --experiment v3 \
  --no-moneyflow
```

## 6. 输出文件

输出目录：

```text
outputs/theme_etf_momentum/v0
outputs/theme_etf_momentum/v1
outputs/theme_etf_momentum/v2
outputs/theme_etf_momentum/v3
```

每个版本输出：

- `theme_etf_momentum_equity_*.csv`
- `theme_etf_momentum_targets_*.csv`
- `theme_etf_momentum_themes_*.csv`
- `theme_etf_momentum_summary_*.csv`
- `theme_etf_momentum_returns_*.png`

本次全量 A 股输出路径：

```text
outputs/theme_etf_momentum/v0/theme_etf_momentum_summary_all_a_v0_20180102_20260622.csv
outputs/theme_etf_momentum/v1/theme_etf_momentum_summary_all_a_v1_20180102_20260622.csv
outputs/theme_etf_momentum/v2/theme_etf_momentum_summary_all_a_v2_20180102_20260622.csv
outputs/theme_etf_momentum/v3/theme_etf_momentum_summary_all_a_v3_20180102_20260622.csv
```

## 7. 实验结果

### 7.1 收益与风险

| 版本 | 总收益 | 年化收益 | 年化波动 | 最大回撤 | Sharpe |
|---|---:|---:|---:|---:|---:|
| V0 | -99.15% | -44.06% | 45.73% | -99.19% | -0.96 |
| V1 | -98.86% | -42.06% | 35.06% | -98.86% | -1.20 |
| V2 | -95.33% | -31.18% | 47.39% | -97.25% | -0.66 |
| V3 | -0.37% | -0.05% | 13.83% | -22.62% | -0.00 |

原始 summary 数据：

```text
V0 total_return=-0.9914748496960739 annual_return=-0.4405946578789832 annual_vol=0.45725026439370225 max_drawdown=-0.9919326982025639 sharpe=-0.9635744190617281
V1 total_return=-0.9886221824932602 annual_return=-0.42055904085066653 annual_vol=0.3505730836315806 max_drawdown=-0.9886221824932602 sharpe=-1.199633002323232
V2 total_return=-0.9533253722022296 annual_return=-0.31175311552677465 annual_vol=0.4738973038856022 max_drawdown=-0.9724693284420469 sharpe=-0.6578495234529361
V3 total_return=-0.003685370744582084 annual_return=-0.0004500216005731694 annual_vol=0.13827547483783345 max_drawdown=-0.22615323581343127 sharpe=-0.003254529417461377
```

### 7.2 目标记录数量

`targets` 文件行数包含表头，实际记录数如下：

| 版本 | targets 记录数 | 信号日期数 | 涉及股票数 |
|---|---:|---:|---:|
| V0 | 7535 | 1972 | 890 |
| V1 | 9428 | 1972 | 959 |
| V2 | 5222 | 1849 | 1451 |
| V3 | 119 | 105 | 106 |

### 7.3 净值记录数量

四个版本的 equity 文件均为 1991 行，包含表头，因此实际净值记录为 1990 条。

## 8. 结论

### 8.1 主题层本身没有 alpha

V0 总收益 `-99.15%`，最大回撤 `-99.19%`。这说明当前“行业主题代理 ETF”层本身非常不可靠。只靠强主题热度做轮动，在全量 A 股长区间里几乎归零。

注意：这里检验的是“行业主题代理”，不是严格意义上的真实 ETF 轮动。由于没有用真实 ETF 份额、ETF 日线、ETF 持仓或跟踪指数成分，不能把这个结论外推为“ETF 轮动无效”。

### 8.2 买强主题成分股也不够

V1 总收益 `-98.86%`，最大回撤 `-98.86%`。相比 V0 没有本质改善。说明“强主题 + 买大市值/高流动性成分股”不是有效策略。

### 8.3 相对强度有改善，但不够

V2 总收益 `-95.33%`，最大回撤 `-97.25%`。相比 V0/V1 略好，但仍然严重亏损。这说明“主题内领涨股”有一点改善方向，但单独使用无法构成可交易策略。

### 8.4 技术择时显著降低回撤，但没有产生正收益

V3 总收益 `-0.37%`，最大回撤 `-22.62%`。相比 V2，回撤从 `-97.25%` 降到 `-22.62%`，说明回踩/突破买点和卖出纪律对风险控制非常有效。

但是 V3 年化收益接近 0，Sharpe 也接近 0。结论是：

```text
择时和风控能避免大亏，但当前主题代理 + 相对强度框架还没有提供足够正 alpha。
```

### 8.5 当前第一版不应直接实盘

原因：

- 真实 ETF 数据未接入，只用了行业代理。
- daily_basic 不是完整逐日快照。
- V0-V2 长区间严重亏损。
- V3 只是控制住回撤，并没有产生正收益。

## 9. 复现步骤

1. 进入项目目录。

```bash
cd /Users/jingansun/Desktop/codex/quant
```

2. 激活环境。

```bash
source activate.sh
```

3. 确认全量 A 股数据目录存在。

```bash
ls data/a_share_qlib
wc -l data/a_share_qlib/instruments/all_a.txt
```

预期 `all_a.txt` 行数为：

```text
5856
```

4. 分别运行四个实验。

```bash
for exp in v0 v1 v2 v3; do
  QLIB_PROVIDER_URI=data/a_share_qlib QLIB_LAZY_TUSHARE=0 \
  python -m strategies.run theme_etf_momentum \
    --market all_a \
    --start 2018-01-02 \
    --end 2026-06-22 \
    --experiment "$exp" \
    --no-moneyflow
done
```

5. 查看 summary。

```bash
for f in outputs/theme_etf_momentum/v*/theme_etf_momentum_summary_all_a_v*_20180102_20260622.csv; do
  echo "$f"
  cat "$f"
done
```

6. 查看目标记录数量。

```bash
for f in outputs/theme_etf_momentum/v*/theme_etf_momentum_targets_all_a_v*_20180102_20260622.csv; do
  echo "$f"
  wc -l "$f"
done
```

## 10. 后续建议

1. 接入真实 ETF 数据后重测 V0。
   - ETF 日线。
   - ETF 份额。
   - ETF 持仓。
   - ETF 跟踪指数成分和权重。

2. 把行业代理替换为“真实 ETF -> 跟踪指数 -> 前 N 大权重股”。

3. 补齐 point-in-time daily_basic。
   - 当前用最近可见缓存文件，严格性不够。

4. 单独测试市场环境过滤。
   - 当前 V3 控制住回撤，但收益不足，可能需要只在指数环境较强时开仓。

5. 对 V3 做参数扫描。
   - 买点 A/B 阈值。
   - `rs_top_pct`。
   - `target_num`。
   - `max_theme_weight`。
   - 止损/移动止盈参数。

6. 恢复资金流增强后再测。
   - 本次为了诚实可复现，使用 `--no-moneyflow`。
   - 如果后续确认 moneyflow/top_inst 缓存完整，可以单独做 V4。
