# ETF Loop Advice Replay Minute Execution

## 1. 口径

- 信号和交易动作来自原引擎 `etf_loop_advice_*.csv`。
- 不按每日 target_weight 强制再平衡，只重放原引擎实际 BUY/SELL。
- 成交价格、容量、滑点、涨跌停和停牌约束用本地分钟数据重新计算。

## 2. 结果

| setting | 资金 | 执行 | 双边bp | 年化 | CAGR | Sharpe | DD | 订单数 | 失败率 | 容量受限 | 均滑点 | 均参与率 | 仓位偏离 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `F2_CAP_MA60` | 1,000,000 | `vwap_0935_1030` | 7 | 104.78% | 173.55% | 3.72 | -10.54% | 347 | 31.70% | 0.00% | 2.20bp | 0.10% | 3.87% |
| `WideA` | 1,000,000 | `vwap_0935_1030` | 7 | 123.62% | 221.12% | 3.36 | -15.50% | 288 | 40.62% | 0.00% | 2.49bp | 0.10% | 4.46% |

## 3. 复现命令

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA,F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 1000000,3000000,5000000,10000000,30000000 --execution-modes vwap_0935_1030 --roundtrip-cost-bps 5,7,10,15,20
```