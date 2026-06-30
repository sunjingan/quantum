# friend9 原始代码对照审计

## 对照对象

- 原始 JoinQuant 代码：`post/62821`，标题“ETF轮动策略 年化163%，回撤7%”。
- 当前聚宽导出脚本：`joinquant_strategies/etf_loop/jq_friend9.py`。
- 本地分钟复现脚本：`runs/etf_loop/run_friend_intraday_replication.py`。

## 关键一致点

| 模块 | 原始代码 | 当前 `jq_friend9.py` |
|---|---|---|
| ETF 池 | 9 只：纳指、日经、德国、黄金、有色、原油、30年国债、红利低波、创业板 | 一致 |
| 调度时间 | `run_daily(trade, '9:50')` | 一致 |
| 持仓数量 | Top1 | 一致 |
| 成本 | `FixedSlippage(0.001)` + 买卖佣金 0.0002，最低 1 元 | 一致 |
| 动态 lookback | `min_days=20`, `max_days=60`, `ratio_cap=0.9` | 一致 |
| 动量打分 | 加权 log 价格回归，`annualized_returns * r2` | 一致 |
| 近期大跌过滤 | con1/con2/con3，触发后 score=0 | 一致 |
| 溢价惩罚 | 前一日 ETF close 与 `unit_net_value`，溢价 >=5% 时 score-1 | 一致 |
| 排名过滤 | `0 < score < 6` | 一致 |
| 交易规则 | 持仓不在目标则卖出；空仓则买入目标 | 一致 |

## 已发现并修复的差异

| 差异 | 之前实现 | 风险 | 当前修复 |
|---|---|---|---|
| ATR 计算 | `jq_friend9.py` 曾使用简化 TR 均值 | 会改变 `short_atr / long_atr`，进而改变动态 lookback 和排名 | 已改回 `import talib` + `talib.ATR(...)` |
| `auto_day=False` 分支 | 之前导出脚本没有简单 25 日 `get_rank` 等价函数 | 如果在聚宽手工切换 `g.auto_day=False` 会失效 | 已补 `rank_friend9_simple` |
| 历史数据读取 | 之前 `safe_history` 使用 `skip_paused=True` 并 `dropna()` | 与原始 `attribute_history(...)` 后再检查 NaN 不完全一致 | 已改为直接 `attribute_history(code, count, '1d', fields)` |

## 本地分钟复现和 JoinQuant 原始代码的天然差异

- 本地复现用本地 1min/5min 数据近似 `current_data[etf].last_price`，默认取 09:50 分钟价格；JoinQuant 实盘/回测的 `last_price` 由平台撮合引擎提供。
- 本地复现用本地 IOPV/单位净值数据估算溢价；JoinQuant 原始代码用 `get_extras('unit_net_value')`。
- 本地复现可以指定成交模式，如 `same_0950_close`、`same_0955_open`、`next_day_open`；JoinQuant 原始代码在 09:50 调用 `order_target_value`，成交由平台撮合模型决定。
- 因此本地分钟复现用于验证容量、成交和滑点，不应期待与 JoinQuant 平台逐笔完全一致。

## 当前结论

当前 `jq_friend9.py` 已经尽量贴近原始 JoinQuant 策略。若要在 JoinQuant 上验证 friend9，应使用当前版本，而不是之前简化 ATR 的版本。
