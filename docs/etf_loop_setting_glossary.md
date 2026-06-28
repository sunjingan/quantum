# ETF Loop Setting Glossary

这份词典解释项目里最常出现的 setting 名称。主线报告里如果只写了参数名，可以对照这里理解它控制的是哪一层。

## 1. 回测与执行

| 参数 | 含义 | 影响 |
|---|---|---|
| `start` / `end` | 回测区间起止日期 | 决定样本长度，所有绩效指标都受它影响 |
| `benchmark` | 比较基准 | 用于计算 alpha、beta、超额收益和基准对照 |
| `open_cost` / `close_cost` | 买入/卖出手续费 | 单边交易成本，直接侵蚀换手较高策略的收益 |
| `slippage` | 固定滑点 | 用来模拟成交价偏离理论价的损耗 |
| `execution_price_mode` | 执行价模式 | 例如 `open`、`vwap`、`close`，决定按什么价格成交 |
| `execution_delay_days` | 成交延迟 | 0 表示当期执行，1 表示次日执行，值越大越保守 |
| `min_trade_value` | 最小成交额 | 小于阈值的订单直接跳过，避免无意义碎单 |
| `participation_cap` | 参与率上限 | 约束单笔下单不能吃掉过多日成交额，防止容量失真 |

## 2. ETF Loop 核心选股

| 参数 | 含义 | 影响 |
|---|---|---|
| `lookback_days` | 动量/回归观察窗口 | 控制排序时回看多长历史，短窗更敏感，长窗更稳定 |
| `holdings_num` | 目标持仓数 | 决定最终买几只，常见是固定 5 只 |
| `mr_ma_period` | 均线过热惩罚窗口 | 用于判断当前价格是否远离中期均线 |
| `mr_penalty` | 过热惩罚强度 | 价格过热时压低得分，防止追高 |
| `use_atr_stop_loss` | 是否启用 ATR 止损 | 用波动率自适应地决定止损线 |
| `atr_multiplier` | ATR 止损倍数 | 倍数越大越宽松，越小越容易止损 |
| `stop_loss_pct` | 固定止损线 | 例如 `0.95` 表示回撤到买入价的 95% 就止损 |
| `use_score_weighting` | 是否按分数加权 | 分数高的标的拿更高权重，不再完全等权 |
| `switch_score_margin` | 换仓分数差门槛 | 新标的必须明显优于旧持仓才换，减少抖动换手 |

## 3. 动态池补漏

| 参数 | 含义 | 影响 |
|---|---|---|
| `dynamic_max_slots` | 动态池最多占几个席位 | 约束动态 PIT 只做补漏，不与静态池平权竞争 |
| `dynamic_max_total_weight` | 动态池总权重上限 | 控制动态池在组合里的最大影响力 |
| `dynamic_score_margin` | 动态候选最小领先幅度 | 动态标的必须显著好于静态最弱入选者才可进入 |
| `dynamic_overheat_threshold` | 动态标的过热阈值 | 买入前涨幅过高时触发额外惩罚 |
| `dynamic_overheat_penalty` | 过热惩罚系数 | 对“追热点追在高位”的动态候选降权 |
| `use_dynamic_pool` | 是否启用动态池 | 关闭时只用静态核心池，打开时才允许 PIT 补漏 |

### `F2_CAP_MA60` 的池子配置

`F2_CAP_MA60` 不是“纯静态池”，它是一个固定的双层基座：

1. 静态核心池：`F2_v3`
2. PIT 月度池补漏：`pit_pools`

对应到参数层，基座里真正决定“池子怎么融合”的参数是：

| 参数 | 取值 | 含义 |
|---|---|---|
| `pit_pools` | G2 PIT 月度池 | 提供按月切换的 PIT 候选集合 |
| `core_pool` | `F2_v3` | 静态核心池，始终保留 |
| `dynamic_fusion_mode` | `capped` | 动态补漏只做受限插入，不做平权并集 |
| `dynamic_max_slots` | `1` | 动态补漏最多只占 1 个席位 |
| `dynamic_max_total_weight` | `0.10` | 动态补漏总权重上限 10% |
| `dynamic_score_margin` | `0.05` | 动态候选必须比静态最弱入选者高出 5% 以上才可替换 |
| `dynamic_overheat_threshold` | `0.10` | 动态候选过去 20 日收益超过 10% 时视为过热 |
| `dynamic_overheat_penalty` | `0.50` | 过热时分数打 5 折，避免追高热点 |
| `use_dynamic_pool` | `False` | 不启用额外的实时动态池构建，只用 PIT + core 的固定基座 |

`F2_CAP_MA60` 另外还叠加了一个独立的过热惩罚层：

| 参数 | 取值 | 含义 |
|---|---|---|
| `mr_ma_period` | `60` | 用 60 日均线判断过热 |
| `mr_threshold` | `1.14` | 价格 / MA60 超过 1.14 时触发惩罚 |
| `mr_penalty` | `0.50` | 过热标的得分打 5 折 |

可以把它理解成两条线：

- **池子线**：`core_pool + pit_pools`，并且 capped 补漏。
- **交易线**：MA60 过热惩罚、止损、调仓、换仓门槛。

所以当你看到 `F2_CAP_MA60`，它的完整含义其实是：

`F2_v3` 静态核心池 + 月度 PIT 补漏（最多 1 席位 / 10% 权重）+ MA60 过热惩罚。

## 4. 动态持仓与暴露拆分

| 参数 | 含义 | 影响 |
|---|---|---|
| `adaptive_window` | 市场状态判断窗口 | 用过去多少天的市场表现决定当前仓位层级 |
| `adaptive_tiers_ret` | 市场状态阈值 | 按基准收益高低划分不同仓位档位 |
| `adaptive_tiers_n` | 每个档位的持仓数 | 决定分散度，不再由总仓位隐式控制 |
| `adaptive_tiers_exposure` | 每个档位的总仓位 | 决定实际买入多少现金，0 代表空仓 |
| `target_holdings` | 目标持仓只数 | V3 里与总仓位拆开，单独控制分散度 |
| `target_exposure` | 目标总仓位 | V3 里与持仓数拆开，单独控制风险暴露 |
| `bench_20d_ret` | 基准 20 日收益状态 | 用于动态持仓判断市场强弱的常用信号 |
| `bench_ma60` | 基准 MA60 状态 | 反应慢，通常比 20dRet 更保守 |
| `bench_vol` | 基准波动率状态 | 主要用于波动环境分类 |
| `portfolio_dd` | 组合回撤状态 | 用自身回撤做风控，但容易过于滞后或失真 |

### `ret_20d` / `bench_20d_ret` 的计算方式

在代码里，`bench_20d_ret` 并不是固定 20 天，而是由 `adaptive_window` 决定回看窗口。

公式是：

`ret_20d = bench_close[t] / bench_close[t - adaptive_window] - 1`

其中：

- `bench_close[t]` 是当前信号日之前可见的基准收盘价。
- `adaptive_window=15` 时，实际就是看过去 15 个交易日的基准涨跌幅。
- 名字里保留 `20d` 只是历史沿用，不代表一定是 20 天。

它的作用不是直接决定买什么 ETF，而是先判断“市场强弱”，再把这个强弱映射成仓位档位。

### 阈值是怎么配合的

`adaptive_tiers_ret`、`adaptive_tiers_n`、`adaptive_tiers_exposure` 是一一对应的三组梯子。

引擎做法是从高到低依次检查阈值，命中第一档就立刻采用那一档的设置：

| 逻辑 | 含义 |
|---|---|
| `ret_20d >= adaptive_tiers_ret[0]` | 采用第 1 档 |
| 否则如果 `ret_20d >= adaptive_tiers_ret[1]` | 采用第 2 档 |
| 否则如果 `ret_20d >= adaptive_tiers_ret[2]` | 采用第 3 档 |
| ... | ... |
| 全都不满足 | 采用最后的 cash / fallback 档 |

这意味着：

- `adaptive_tiers_n` 控制“买几只”。
- `adaptive_tiers_exposure` 控制“总仓位买多少”。
- 两者可以同时变，也可以只改其中一个。

例如：

- `adaptive_tiers_ret=0.05,0.02,0.00,-0.03,-0.06`
- `adaptive_tiers_n=5,5,4,4,3,0`
- `adaptive_tiers_exposure=1,1,0.8,0.6,0.4,0`

对应关系可以理解为：

| 基准 15d 收益 | 持仓数 `n` | 总仓位 `exposure` |
|---|---:|---:|
| `>= 5%` | 5 | 100% |
| `>= 2%` 且 `< 5%` | 5 | 100% |
| `>= 0%` 且 `< 2%` | 4 | 80% |
| `>= -3%` 且 `< 0%` | 4 | 60% |
| `>= -6%` 且 `< -3%` | 3 | 40% |
| `< -6%` | 0 | 0% |

这正是你说的 V3 思路：

- 市场弱时，先降 `target_exposure`。
- `target_holdings` 不要和仓位一起过度收缩。
- 这样可以避免“弱市里变成满仓押 1 只 ETF”。

### WideA / WideB

这两个名字都来自 `bench_20d_ret` 模式下的两套阈值梯子，都是“只改阈值，不改策略框架”的对照组。

- `WideA`: `adaptive_window=15`，`adaptive_tiers_ret=0.06,0.03,0.00,-0.02,-0.05,-0.08`，`adaptive_tiers_n=5,5,4,3,2,1,0`
- `WideB`: `adaptive_window=15`，`adaptive_tiers_ret=0.05,0.01,-0.02,-0.05,-0.08,-0.12`，`adaptive_tiers_n=5,5,4,3,2,1,0`

含义上：

- `WideA` 比 `Current` 更平滑，弱市里不会太快把持仓压到很低，属于更保守的参考梯。
- `WideB` 比 `WideA` 更宽松，阈值整体再往下移一档，目的是测试“更晚降仓/更晚空仓”是否还能撑住收益。
- 两者都不是新的选股方法，只是同一套 `bench_20d_ret` 逻辑下不同的仓位分层规则。

注：`bench_20d_ret` 这个名字是历史沿用，实际回看天数由 `adaptive_window` 决定。V3 主线里常用的是 `adaptive_window=15`，所以它实际是在看 15 个交易日的基准收益。

### V3 的两条配置线

V3 里其实分成两条独立配置线：

- `adaptive_tiers_n` 这一条，只管“持仓数”。
- `adaptive_tiers_exposure` 这一条，只管“总仓位”。

`Current`、`WideA`、`WideB` 主要是在 `n` 的梯子上做对照；`Exph_*` 则是在 `n` 的基础上继续拆 `exposure`。

它们都建立在 `F2_CAP_MA60` 这个基座上，也就是：

- 静态核心池：`F2_v3`
- 再叠加 capped 的 PIT 补漏逻辑
- 然后才是 V3 的动态持仓 / 暴露规则

所以这些实验不是“纯静态池只改持仓数”，而是“同一个 F2_CAP_MA60 基座上，测试不同的市场自适应仓位规则”。

## 5. 调仓稳定性

| 参数 | 含义 | 影响 |
|---|---|---|
| `rebalance_frequency` | 调仓频率 | 每日、每 2 日、每周等，越频繁换手越高 |
| `topk` / `target_num` | 候选选择数量 | 有些脚本里表示 top-k 候选，不一定等于最终持仓数 |
| `min_hold_days` | 最短持有期 | 防止短期噪声导致过快卖出 |
| `max_turnover_pct` | 单次换手上限 | 限制一次调仓不能把仓位全打散 |
| `score_weighting` | 按得分分配仓位 | 与 `use_score_weighting` 同类，强调高分标的 |

## 6. 如何看这些参数

原则上只看两类关系：

1. 哪个参数在控制“选谁买”。
2. 哪个参数在控制“买多少、买几只、何时卖”。

如果两个参数同时影响同一件事，就容易混淆。例如：

- `adaptive_tiers_n` 控制持仓数。
- `adaptive_tiers_exposure` 控制总仓位。
- `dynamic_max_slots` 控制动态池最多插入几个名额。

这三者不要混着改，否则很难判断收益变化来自选股、暴露，还是分散度。
