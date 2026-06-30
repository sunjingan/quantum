# JoinQuant ETF Loop scripts

本目录由 `tools/export_joinquant_strategies.py` 生成，用于把本地 ETF Loop 候选策略复制到聚宽回测/模拟盘。

聚宽 API 核对来源：

- `https://www.joinquant.com/help/api/help#name:api`
- 实际内容接口：`https://www.joinquant.com/help/api/getContent?name=api`

本适配使用聚宽文档中的 `initialize`、`run_daily`、`attribute_history`、`get_price`、`get_extras`、`get_current_data`、`order_target_value`、`set_option('avoid_future_data', True)`、`set_slippage`、`PriceRelatedSlippage/FixedSlippage`、`set_order_cost/OrderCost`。

## 脚本

- `jq_F2_CAP_MA60.py`: F2_v3 核心池 + G2 PIT 月度动态池 + capped 动态补漏 + MA60 过热惩罚，Top5。
- `jq_WideA.py`: 在 `F2_CAP_MA60` 基础上加入 HS300 15 日收益的动态持仓数，参数为 `0.06,0.03,0,-0.02,-0.05,-0.08 -> 5,5,4,3,2,1,0`，总仓位恒为 100%。
- `jq_Exph_v3_exp_looser.py`: 在 `F2_CAP_MA60` 基础上加入 v3 的“总仓位”和“持仓数”分离规则，参数为 `0.05,0.02,0,-0.03,-0.06 -> N 5,5,4,4,3,0 -> exposure 1,1,0.85,0.65,0.45,0`。
- `jq_friend9.py`: friend 原始 9 ETF，Top1，ATR 动态 lookback，溢价惩罚，近期大跌过滤，09:50 运行。
- `jq_F2_CAP_MA60_current_month.py` / `jq_WideA_current_month.py` / `jq_Exph_v3_exp_looser_current_month.py`: 聚宽编辑器精简版，只写死当前月动态池，不包含 2018-2026 历史 PIT 大字典。
- `jq_WideA_fixed10.py`: 固定 10 ETF 池版本，只保留 WideA 打分和动态持仓，不启用动态 PIT 补漏。

## 重要差异

- F2/WideA/Exph 在聚宽版中于 `09:35` 运行，日线信号使用 `attribute_history` 在当前分钟可见的历史日线数据，不显式读取当天收盘价。
- F2/WideA/Exph 的 G2 PIT 月度动态池已经嵌入脚本；2026-06 会默认合并手工推荐 10 ETF 池。若要严格复现历史报告，把脚本里的 `g.use_manual_current_month_pool` 改成 `False`。
- 本地引擎使用复权后的 Tushare 日线口径；聚宽 `use_real_price=True` 下可能与本地复权口径略有差异，回测结果不应期望逐日完全一致。
- 当前聚宽脚本默认 `g.rebalance_existing=False`，即持有标的仍在目标池中就不强制调仓，贴近“在 top5 里继续持有”的模拟盘逻辑。
- F2/WideA/Exph 成本按本地候选口径设置：佣金 `1.5bp/边`，滑点 `2bp/边`。聚宽 `PriceRelatedSlippage(x)` 的 `x` 是买卖价差，脚本设置为 `0.0004`，买入/卖出各承担 `0.0002`。
- friend9 保留原始聚宽代码口径：`FixedSlippage(0.001)` + `open_commission/close_commission=0.0002`。
- 本地分钟执行层里的窗口参与率、拆单失败、连续冲击滑点、涨跌停阻断等是压力测试逻辑，不硬编码到聚宽模拟盘脚本。聚宽平台本身会按其撮合/滑点/交易成本模型执行；如果还想验证拆单，可以复制脚本后把 `run_daily(trade, '09:35')` 改成多个时点并自行拆分目标金额。
- `*_current_month.py` 只适合从当前月开始做聚宽平台回测/模拟盘准入。不要用它解释 2013-2026 研究回测，因为历史 PIT 动态池已被替换成当前月写死池。

## 使用

在 JoinQuant 新建策略/模拟盘账户，建议账户名：

- `F2_CAP_MA60_paper`
- `WideA_paper`
- `Exph_v3_exp_looser_paper`
- `friend9_paper`
- `WideA_fixed10_paper`

分别复制对应 `.py` 脚本到聚宽，先跑平台回测，再开模拟盘。

如果聚宽编辑器无法接受完整 PIT 版的大脚本，优先复制 `*_current_month.py`。
