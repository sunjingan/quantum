# friend9 候选策略模拟盘前验证报告

更新时间：2026-06-29

详细数据位置：

- 详细验证报告：`outputs/etf_loop/friend9_validation/friend9_validation_report.md`
- 汇总 CSV：`outputs/etf_loop/friend9_validation/friend9_validation_summary.csv`
- 逐笔增强交易日志：`outputs/etf_loop/friend9_validation/trades_enriched_*.csv`
- 执行手册：`outputs/etf_loop_paper/execution_playbook.md`

复现命令：

```bash
source activate.sh && python runs/etf_loop/run_friend9_validation.py --start 2020-01-01 --end 2026-06-25 --force
```

## 1. 验证对象

friend9 是一个独立候选策略，不是 `F2_CAP_MA60` / `WideA` 的执行层替代。

策略定义：

- ETF 池：friend 原始 9 只跨资产 ETF。
- 信号：09:50 使用当时可见数据计算 `jq_auto` 动量分数。
- 回溯窗口：基于 ATR 的 20-60 日动态 lookback。
- 持仓数：Top1。
- 成本：JoinQuant 风格，买卖各 2bp 佣金，叠加 `FixedSlippage(0.001)` 元/份。
- 交易：目标变化时卖出旧 Top1，买入新 Top1。

## 2. 核心结果

2020-01-01 到 2026-06-25：

| 执行方式 | 资金 | 年化 | Sharpe | DD | 单边全成本 |
|---|---:|---:|---:|---:|---:|
| `same_0951_open` | 50,000 | 47.02% | 1.67 | -24.45% | 7.09bp |
| `same_0955_open` | 50,000 | 47.66% | 1.69 | -24.62% | 7.10bp |
| `next_day_open` | 50,000 | 46.52% | 1.59 | -21.42% | 7.21bp |

解读：

- friend9 的收益并不只依赖 `09:50` 同 bar 成交；`09:51`、`09:55`、甚至次日开盘下收益仍高。
- 但回撤在 `-21%` 到 `-25%`，这不是低波策略。
- `FixedSlippage(0.001)` 折算后单边全成本约 `7.1bp`，双边约 `14.2bp`，高于我们日线候选常用的双边 `7bp`。
- 注意：本节结果没有把“超过窗口参与率上限的未成交部分”反馈到账户净值里，只是理想成交 + 容量诊断口径。要和 WideA realistic replay 可比，必须看下面的 partial-fill replay。

## 2.1 同等窗口参与率 partial-fill replay

新增脚本：

```bash
source activate.sh && python runs/etf_loop/run_friend9_partial_fill_replay.py --start 2020-01-01 --end 2026-06-25 --capitals 50000,100000,500000,1000000 --fill-modes same_0955_open,next_day_open --max-participation 0.10
```

输出：

- `outputs/etf_loop/friend9_validation/friend9_partial_fill_summary_20200101_20260625.csv`
- `outputs/etf_loop/friend9_validation/friend9_partial_fill_report.md`

口径：

- 每笔订单最多成交 `09:35-10:30` 窗口成交额的 `10%`。
- 未成交部分不强行补齐；卖不掉则保留旧仓，买不满则保留现金。
- 这是和 WideA realistic replay 可比的 stateful 压力测试。

| 执行方式 | 资金 | 年化 | Sharpe | DD | 失败率 | 均成交率 |
|---|---:|---:|---:|---:|---:|---:|
| same_0955_open | 50,000 | 39.89% | 1.54 | -22.83% | 7.28% | 91.04% |
| same_0955_open | 100,000 | 40.09% | 1.55 | -22.82% | 3.64% | 93.57% |
| same_0955_open | 500,000 | 28.78% | 1.03 | -39.84% | 6.85% | 87.68% |
| same_0955_open | 1,000,000 | 27.06% | 0.99 | -41.48% | 7.28% | 85.70% |
| next_day_open | 50,000 | 38.35% | 1.15 | -42.57% | 15.05% | 83.28% |
| next_day_open | 100,000 | 35.41% | 1.11 | -42.57% | 13.76% | 83.49% |
| next_day_open | 500,000 | 31.78% | 1.10 | -42.57% | 6.45% | 85.52% |
| next_day_open | 1,000,000 | 28.84% | 1.04 | -42.57% | 9.46% | 80.96% |

结论：

- friend9 在小资金 `5万-10万` 下，经 partial-fill 后仍然强，明显值得影子盘观察。
- `50万-100万` 下，收益仍高，但回撤扩大到约 `-40%`，不能直接放大。
- 和 WideA 同区间同压力相比：friend9 小资金更强；大资金收益略高但路径风险更大。

## 3. 最大问题：容量

容量约束比收益本身更关键。

以 `09:35-10:30` 窗口参与率 `<=10%` 为约束：

| 资金 | `same_0955_open` 窗口>10%比例 | p95拆单份数 | 最大拆单份数 |
|---:|---:|---:|---:|
| 50,000 | 6.64% | 1.2 | 52.8 |
| 100,000 | 12.42% | 2.4 | 105.8 |
| 500,000 | 27.84% | 11.9 | 528.8 |
| 1,000,000 | 38.76% | 23.9 | 1057.9 |
| 3,000,000 | 58.67% | 71.7 | 3173.7 |

结论：

- `5万` 资金可以进入影子盘或极小资金模拟盘，但仍有少量交易需要拆单或跳过。
- `10万` 开始已经有明显容量压力。
- `50万+` 不适合按回测假设直接全仓成交。
- `100万+` 必须引入严格部分成交和跨日未完成订单处理，否则回测收益不可实盘拿到。

## 4. 订单拆分方案

### 4.1 默认执行窗口

friend9 推荐执行窗口：

```text
09:50 生成信号
09:55 - 10:30 执行
```

不用 `09:50` 同 bar 成交作为实盘默认，因为这会混入乐观成交假设。

### 4.2 默认拆单规则

每笔订单计算：

```text
max_fill_value = 09:35-10:30 窗口成交额估计值 * 10%
```

如果：

```text
order_value <= max_fill_value
```

可以在当天窗口内分 4 笔完成：

```text
09:55 25%
10:05 25%
10:15 25%
10:25 25%
```

如果：

```text
order_value > max_fill_value
```

只成交：

```text
filled_value = max_fill_value
```

剩余部分：

```text
不追价
不强行补齐
记录 unfilled_value
保留现金或保留原持仓
```

### 4.3 分钟级二次约束

每个子订单还要满足：

```text
child_order_value <= 最近 5 分钟成交额的 20%-30%
```

否则继续缩小订单，或跳过该时间片。

### 4.4 买卖顺序

目标变化时：

```text
1. 先卖出旧持仓。
2. 卖出成功多少，就释放多少现金。
3. 再买入新目标。
4. 旧仓卖不掉时，不强行买新目标到满仓。
```

这会导致实际持仓和回测目标不同，所以必须记录：

```text
target_position
actual_position
target_exposure
actual_exposure
unfilled_sell_value
unfilled_buy_value
```

## 5. 挂单价格

friend9 使用限价单，不用市价单。

买入：

```text
buy_limit = min(卖一价 + 0.001, mid_price * 1.001)
```

卖出：

```text
sell_limit = max(买一价 - 0.001, mid_price * 0.999)
```

如果是跨境 ETF / 商品 ETF / 盘口薄 ETF，可人工放宽到：

```text
max_slippage = 0.20%
```

但必须写入日志，不作为默认。

## 6. 风控和跳过规则

以下情况不买入：

- 前一日溢价率 `>=5%`，除非人工确认可接受。
- 当前卖一为空。
- 最近 1 分钟无成交。
- 09:35-10:30 窗口成交额为 0 或缺失。
- 买入接近涨停。
- 订单按 10% 窗口参与率拆分后仍无法完成主要部分。

以下情况不强行卖出：

- 当前买一为空。
- 最近 1 分钟无成交。
- 卖出接近跌停。
- 盘口断层导致限价单无法成交。

这些情况发生时，保留旧仓或现金，并记录为执行偏差。

## 7. 当前是否可以进入模拟盘

结论：可以进入影子盘，不建议直接实盘放大。

建议阶段：

| 阶段 | 资金 | 是否下单 | 目标 |
|---|---:|---|---|
| 阶段 1 | 0 | 不下单 | 每天 09:50 生成信号，记录理论订单和实际盘口 |
| 阶段 2 | 1万-5万 | 可小额下单 | 验证限价成交、撤单、部分成交、滑点 |
| 阶段 3 | 5万-10万 | 谨慎 | 只有阶段 2 连续稳定后再考虑 |
| 阶段 4 | 50万+ | 暂不建议 | 当前容量测试不支持直接放大 |

## 8. 模拟盘必须记录的字段

每笔订单：

```text
signal_date
signal_time
trade_time
ts_code
side
target_value
order_value
child_order_value
limit_price
best_bid
best_ask
mid_price
last_price
filled_value
filled_price
fill_ratio
cancel_reason
premium_rate
minute_amount
window_amount_0935_1030
participation_window
participation_minute
slippage_bp
commission
```

每日组合：

```text
portfolio_value
cash
cash_ratio
target_holding
actual_holding
target_exposure
actual_exposure
unfilled_value
execution_error
```

## 9. 后续补测

还需要继续做三件事：

1. 用真实盘口数据验证 `卖一+0.001 / 买一-0.001` 是否真的能成交。
2. 在回测里加入“参与率上限导致部分成交/未成交”的状态机，而不是只做容量诊断。
3. 对 43 笔 `premium>=5%` 的交易逐笔复核，判断是否应该禁买或降权。

当前 friend9 的定位：

```text
高收益候选，适合影子盘和小资金验证；
不适合作为无需执行约束就直接放大的实盘策略。
```
