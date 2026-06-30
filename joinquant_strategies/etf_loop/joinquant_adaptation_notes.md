# 聚宽适配说明

## 文档核对

核对入口：

- `https://www.joinquant.com/help/api/help#name:api`
- 静态页实际内容接口：`https://www.joinquant.com/help/api/getContent?name=api`

本目录脚本只使用聚宽策略文档中的标准策略 API：`initialize`、`run_daily`、`attribute_history`、`get_price`、`get_extras`、`get_current_data`、`order_target_value`、`set_option`、`set_slippage`、`PriceRelatedSlippage/FixedSlippage`、`set_order_cost/OrderCost`。

## 未来函数处理

- 所有 ETF Loop 候选脚本都设置 `set_option('avoid_future_data', True)`。
- `F2_CAP_MA60`、`WideA`、`Exph_v3_exp_looser` 在 `09:35` 运行，日线信号用 `attribute_history(..., '1d', ...)` 取当前时点之前可见的历史日线数据，不显式读取当天收盘价。
- `friend9` 保持原始策略的 `09:50` 运行方式，会把 `get_current_data()[etf].last_price` 作为当时已知价格加入动量计算；这不是收盘未来函数，但回测频率应使用分钟级，否则平台可能无法真实表达 09:50 盘中价格。

## 动态池处理

聚宽平台不方便从本地 pickle/CSV 动态加载月度池，因此脚本生成时已把 `G2 PIT` 月度动态池直接写入 `.py` 文件。

- `DYNAMIC_PIT_POOLS`：来自本地 `data/tushare_cache/sector_prosperity/etf_pool_G2_PIT_monthly.pkl`。
- `MANUAL_DYNAMIC_POOL_202606`：合并用户给出的 2026-06 手工动态池。
- 如果要严格复现历史报告，不使用手工 2026-06 池，把 `g.use_manual_current_month_pool = False`。

## 成本与滑点

`F2_CAP_MA60`、`WideA`、`Exph_v3_exp_looser` 使用候选策略默认成本：

- 佣金：`open_commission=0.00015`、`close_commission=0.00015`，即 `1.5bp/边`。
- 滑点：`PriceRelatedSlippage(0.0004)`。
- 聚宽文档说明百分比滑点参数是买卖价差，买单按执行时价格加一半，卖单按执行时价格减一半。因此 `0.0004` 对应单边约 `2bp`。

`friend9` 保持原作者聚宽代码：

- `FixedSlippage(0.001)`。
- `open_commission=0.0002`、`close_commission=0.0002`。

## 为什么不硬编码本地分钟压力测试

本地 `candidate_execution_validation_report.md` 里的窗口参与率、拆单失败、连续冲击滑点、涨跌停阻断，是为了验证“日线 alpha 能否被真实执行拿到”的研究压力测试。

聚宽模拟盘本身有撮合、交易成本、滑点模型。如果把本地压力测试再硬编码进策略，容易双重惩罚，也会让平台回测和真实模拟盘不一致。因此当前聚宽脚本只实现“信号和目标仓位”，执行层交给聚宽平台。

如果后续要在聚宽里测试拆单，建议复制 `jq_WideA.py` 后做一个单独实验版本：保留同一套信号，在多个 `run_daily` 时点分批调用 `order_target_value`，不要覆盖当前候选脚本。

