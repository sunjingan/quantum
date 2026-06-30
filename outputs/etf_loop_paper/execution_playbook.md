# ETF 候选策略模拟盘/实盘执行手册

更新时间：2026-06-29

本文只讨论交易执行，不重新选择策略。当前需要分开处理两类候选：

- `friend9`：日内 09:50 信号策略，Top1，依赖分钟数据。
- `F2_CAP_MA60` / `WideA`：日线收盘信号策略，T 日收盘后出信号，T+1 执行。

两类策略不能混用同一种执行方式。`friend9` 可以 09:50 生成信号；`F2_CAP_MA60` / `WideA` 不应该 09:50 重新算信号追单。

## 1. 通用原则

### 1.1 禁止事项

- 不用信号日收盘价成交。
- 没有成交日可用价格时不成交，不做 fallback。
- 不用市价单无上限追价。
- 不在溢价、盘口、成交额异常时强行买入。
- 不为了“回测满仓”而在实盘里强行补齐仓位。

### 1.2 默认订单类型

优先使用限价单，不用市价单。

买入限价：

```text
buy_limit = min(卖一价 + 0.001, mid_price * (1 + max_slippage))
```

卖出限价：

```text
sell_limit = max(买一价 - 0.001, mid_price * (1 - max_slippage))
```

其中：

```text
mid_price = (买一价 + 卖一价) / 2
max_slippage 默认 0.10%
跨境 ETF / 商品 ETF / 盘口薄 ETF 可放宽到 0.20%，但必须记录原因
```

如果无法获取买一/卖一，只能用最近成交价做影子盘记录，不能真实下单。

### 1.3 成交失败处理

默认规则：

```text
挂单 30-60 秒未成交 -> 撤单
重新读取盘口 -> 重新挂一次
累计重挂 3 次仍未成交 -> 停止追价，记录未成交
```

不允许无限追单。未成交本身就是模拟盘/实盘需要验证的风险。

## 2. friend9 执行流程

### 2.1 信号时间

friend9 的信号逻辑是：

```text
09:50 使用截至当时可见的日线历史 + 09:50 附近盘中价格
计算 9 只 ETF 的 jq_auto 动量分数
选择 Top1
```

推荐模拟盘使用：

```text
09:50:00-09:50:10 冻结数据并生成信号
09:51 或 09:55 开始执行
```

不要把 `09:50 close` 同时当作信号价和成交价。这个假设偏乐观。

### 2.2 推荐成交时间

当前推荐分两档：

| 模式 | 用途 | 说明 |
|---|---|---|
| `09:55 单次/分批` | 默认模拟盘 | 比 09:50 更现实，仍然能跟上日内信号 |
| `09:51 小额试单` | 高敏感观察 | 适合影子盘或极小资金验证 |

不建议一开始直接按 `09:50` 同 bar 成交。

### 2.3 friend9 挂单价格

friend 原始 JoinQuant 成本近似为：

```text
佣金 2bp/边
FixedSlippage 0.001 元/份/边
```

所以实盘/模拟盘可先用：

```text
买入限价 = 卖一价 + 0.001
卖出限价 = 买一价 - 0.001
```

再加一层最大滑点保护：

```text
买入限价不能高于 mid_price * 1.001
卖出限价不能低于 mid_price * 0.999
```

如果是跨境 ETF、商品 ETF，且盘口稳定，可临时放宽到 `0.2%`，但必须写入交易日志。

### 2.4 friend9 订单拆分

friend9 是 Top1 轮动，单笔换仓金额可能很大。不能把回测里的“全仓一次成交”直接搬到实盘。

默认拆单窗口：

```text
09:55 - 10:30
```

默认参与率约束：

```text
单笔成交金额 <= 09:35-10:30 窗口成交额的 10%
单笔成交金额 <= 过去 20 日日均成交额的 3%
```

拆单方式：

```text
1. 先卖出旧持仓。
2. 卖出完成或部分完成后，再买入新目标。
3. 每 3-5 分钟切一笔。
4. 每笔订单不超过当时估计窗口容量的 10%。
5. 10:30 后未完成部分不继续追，保留现金或保留旧仓。
```

如果需要更保守：

```text
09:55 成交 25%
10:05 成交 25%
10:15 成交 25%
10:25 成交 25%
```

如果盘口很薄：

```text
单笔订单金额 <= 最近 5 分钟成交额的 20%-30%
否则继续拆小或跳过
```

### 2.5 friend9 交易跳过规则

以下情况不买入：

- 前一日溢价率 `>= 5%`，除非人工确认是可接受的跨境/商品 ETF 溢价。
- 目标 ETF 当前卖一为空、盘口明显断层、最近 1 分钟无成交。
- 买入价接近涨停。
- 订单金额超过容量约束，且拆单后预计无法在 10:30 前完成。
- 数据缺失：09:50 价格、买一卖一、成交额、单位净值缺一项。

以下情况不强行卖出：

- 当前买一为空或最近 1 分钟无成交。
- 卖出价接近跌停。
- 旧仓无法合理成交时，允许保留旧仓，并记录“调仓失败”。

## 3. F2_CAP_MA60 / WideA 执行流程

### 3.1 信号时间

这两条策略是日线策略：

```text
T 日收盘后生成目标持仓
T+1 执行交易
```

推荐时间：

```text
T 日 15:10 后生成明日订单计划
T+1 日 09:35-10:30 分批执行
```

不要在 T+1 09:50 重新按盘中价格生成新信号。

### 3.2 执行顺序

```text
1. 读取昨日收盘后生成的 target_position。
2. 检查当前持仓和目标持仓差异。
3. 先卖出不在目标池里的 ETF。
4. 再买入新增 ETF。
5. 已持有且仍在目标里的 ETF 原则上不动，除非权重偏离过大。
```

### 3.3 推荐挂单

默认执行窗口：

```text
09:35 - 10:30
```

默认拆分：

```text
09:35 25%
09:45 25%
10:00 25%
10:20 25%
```

挂单价格：

```text
买入限价 = min(卖一价 + 0.001, mid_price * 1.001)
卖出限价 = max(买一价 - 0.001, mid_price * 0.999)
```

如果成交不足：

```text
10:30 前最多重挂 3 次
未成交部分保留现金或保留原仓
不追到超过滑点上限
```

### 3.4 WideA 特别说明

WideA 有动态持仓/市场弱时降仓逻辑。实盘时必须尊重 `target_exposure`：

```text
target_exposure < 100% 时，多余资金留现金
不要为了“资金闲着可惜”额外买 ETF
```

## 4. 日志字段要求

模拟盘/实盘每笔订单至少记录：

```text
strategy
signal_date
signal_time
trade_date
order_time
ETF code
ETF name
side
target_weight
current_weight
target_value
order_value
limit_price
best_bid
best_ask
mid_price
last_price
filled_value
filled_price
fill_ratio
cancel_reason
slippage_bp
commission
premium_rate
minute_amount
window_amount_0935_1030
participation_minute
participation_window
participation_daily
is_cross_border
is_commodity
is_near_limit
data_missing_flag
manual_override
```

每日组合日志至少记录：

```text
date
strategy
portfolio_value
cash
cash_ratio
holdings
target_holdings
target_exposure
actual_exposure
orders_submitted
orders_filled
orders_cancelled
unfilled_value
slippage_total
commission_total
notes
```

## 5. 当前建议

### friend9

可以进入影子盘，但只建议先用小资金或不下单影子盘验证：

```text
默认信号：09:50
默认执行：09:55-10:30 分批
默认资金：5 万或更低
默认容量：窗口参与率 <= 10%
默认价格：买卖一档 + 0.001，且不超过 0.1%-0.2% 滑点上限
```

friend9 的主要风险不是回测收益，而是容量和真实成交。

### F2_CAP_MA60 / WideA

更适合作为稳定模拟盘主线：

```text
T 日收盘信号
T+1 09:35-10:30 TWAP
严格记录 actual_position vs target_position
允许部分成交和现金偏离
```

如果只跑一个模拟盘主策略，优先 `WideA`。如果同时观察高收益候选，可把 `friend9` 作为独立影子盘，不要和 WideA 混仓。
