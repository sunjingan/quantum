# friend9 原始 JoinQuant 代码与本地复现对照审计

## 审计对象

- 原始代码：用户提供的 JoinQuant `post/62821` friend ETF 轮动策略。
- 报告对象：`outputs/etf_loop/friend_intraday_comparison/friend_intraday_experiment_summary.md` 中的 “Friend 原始 9-ETF 日内复现”。
- 本地实现：`runs/etf_loop/run_friend_intraday_replication.py` 中的 `jq_simple` / `jq_auto` 分支。

## 总结

报告里的 `full_friend_logic / jq_auto` 方向是对的，主体逻辑与原始代码一致：9 ETF 池、09:50 信号、Top1、ATR 动态 lookback、溢价惩罚、近期大跌过滤、JoinQuant 风格固定滑点和基金佣金。

但它不是 JoinQuant 引擎的逐笔复刻，而是用本地 1min/5min 数据做的近似复现。最重要的差异是：原始代码在 09:50 调用 `current_data[etf].last_price` 并下单，由 JoinQuant 平台撮合；本地报告用分钟 K 线的 09:50 close / 09:51 open / 09:55 open 等多个 fill mode 近似。

## 逐项对照

| 模块 | 原始 JoinQuant 代码 | 报告里的本地 friend9 复现 | 结论 |
|---|---|---|---|
| ETF 池 | 9 只：纳指、日经、德国、黄金、有色、原油、30年国债、红利低波、创业板 | `FRIEND_POOL_9` 同样 9 只 | 一致 |
| 调度时间 | `run_daily(trade, '9:50')` | `signal_time=09:50` | 一致 |
| 持仓数量 | `target_num = 1` | `holdings_num=1` / Top1 | 一致 |
| 成本 | `FixedSlippage(0.001)` + 买卖佣金 0.0002，最低 1 元 | `exact_jq_cost=True` 时用固定 0.001 元/份 + 2bp 佣金，最低 1 元 | 基本一致 |
| 简单排名 | `get_rank`: 25 日 close + 当前 last_price | `jq_simple`: 25 日 close + 09:50 分钟信号价 | 逻辑一致，价格源近似 |
| 完整排名 | `get_rank2`: ATR 动态 lookback 20-60 | `jq_auto`: ATR 动态 lookback 20-60 | 逻辑一致 |
| ATR | `talib.ATR` | 本地用 Wilder ATR 实现；当前环境没有 `talib` | 应非常接近，但非逐函数完全一致 |
| 溢价 | 前一交易日 close vs `get_extras('unit_net_value')` | 本地单位净值数据近似 `unit_net_value` | 数据源可能有差异 |
| 近期大跌过滤 | con1 / con2 / con3，触发 score=0 | 同样 con1 / con2 / con3 | 一致 |
| 排名过滤 | `0 < score < 6` | 同样 `0 < score < 6` | 一致 |
| 卖出 | 当前持仓不在 target 则卖出 | 当前持仓不等于 Top1 则卖出 | 一致 |
| 买入 | 空仓时用可用现金买目标 | 空仓时全仓买目标 | 一致 |

## 已修复的本地实现问题

本次修复了 `runs/etf_loop/run_friend_intraday_replication.py` 中一个潜在数据对齐问题：

- 修复前：`close`、`high`、`low` 分别 `dropna().tail(max_days+10)`，理论上可能取到不同日期序列。
- 修复后：先按日期拼成同一个 OHLC 表，再 tail 和计算 ATR，更接近 JoinQuant `attribute_history` 返回的逐日行数据。

这属于复现精度修复，不改变 friend 原始策略意图。

## 未来函数与数据污染检查

### 原始 JoinQuant 代码

未发现明确未来函数：

- `attribute_history(..., "1d", ...)` 在 `avoid_future_data=True` 下，09:50 调用应只返回当前时点之前的历史日线。
- `current_data[etf].last_price` 是 09:50 当时可见价格，不是未来收盘价。
- `get_price(... context.previous_date ...)` 和 `get_extras(... context.previous_date ...)` 只取前一交易日数据。
- 交易在 09:50 之后下单，信号和交易同日发生，属于日内策略设定，不是天然未来函数。

### 本地报告中的复现

需要区分 fill mode：

| fill mode | 是否建议作为严肃结果 | 原因 |
|---|---|---|
| `same_0950_close` | 不建议 | 信号和成交都使用 09:50 close；如果本地分钟时间戳代表完整 09:50 K 线收盘，这有同分钟 bar lookahead 风险。 |
| `same_0951_open` | 可作为较激进 T+0 近似 | 信号用 09:50，成交用 09:51 open，避免完全同一根 K 线成交。 |
| `same_0955_open` | 更适合作为保守 T+0 近似 | 给信号生成和下单留出 5 分钟，更接近可执行影子盘。 |
| `next_day_open` | 延迟压力测试 | 不是 friend 原始意图，只用于看 alpha 是否依赖日内即时执行。 |

因此，报告里 `same_0950_close` 的高收益不应直接作为实盘候选依据；如果要模拟盘，优先看 `same_0951_open` 或 `same_0955_open`，并继续叠加容量、拆单、参与率、溢价审计。

## 原始代码本身的小问题

- 注释写“三天内每天都跌，总共跌超4%”，但代码条件是 `prices[-1]/prices[-4] < 0.95`，实际是跌超 5%。这是注释不一致，不是未来函数。
- `current_data[etf].last_price` 与 `order_target_value` 同在 09:50 使用，回测结果会依赖 JoinQuant 的日内撮合模型；这不是未来函数，但可能高估真实可成交价格。
- 溢价惩罚只在溢价大于等于 5% 时 score 减 1，不是硬过滤；高溢价 ETF 仍可能入选，如果原始 score 足够高。

## 当前结论

- `friend_intraday_experiment_summary.md` 中 friend9 的主体策略实现与原始代码基本一致。
- 最需要谨慎的是报告中 `same_0950_close` 的解释：它偏乐观，可能带同分钟 K 线未来信息；不要用它作为实盘预期。
- 更可信的本地近似是 `full_friend_logic / jq_auto / same_0951_open` 和 `same_0955_open`。
- 若最终在 JoinQuant 上开模拟盘，应以当前 `joinquant_strategies/etf_loop/jq_friend9.py` 为准，让平台自己执行 09:50 的 `current_data` 和撮合逻辑。
