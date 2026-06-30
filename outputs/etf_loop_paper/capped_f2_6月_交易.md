# capped_f2 6月模拟交易记录

## 当前使用的 ETF 池

- 策略名：`capped_f2`
- 初始资金：`500,000`
- 信号日：`2026-06-29` 收盘后
- 计划交易日：`2026-06-30`
- 核心池：`F2_v3`
- 动态池：`G2 PIT 月度动态池 + 手工推荐池`，合并模式 `merge`
- 动态池约束：动态独有标的最多 `1` 个席位，动态独有总权重最多 `10%`
- 动态过热惩罚：买入前 20 日涨幅超过 `10%` 时，动态独有标的 score 乘以 `0.5`
- 本次 active pool：`52` 只；核心池 `44` 只；原 PIT 动态池 `35` 只；手工池 `10` 只；合并后有效动态池 `43` 只

| ts_code | 名称 | 来源 |
|---|---|---|
| 159201.SZ | 华夏国证自由现金流ETF | core+dynamic |
| 159206.SZ | 永赢国证商用卫星通信产业ETF | dynamic |
| 159399.SZ | 国泰富时中国A股自由现金流聚焦ETF | core+dynamic |
| 159516.SZ | 国泰中证半导体材料设备主题ETF | core+dynamic |
| 159518.SZ | 嘉实标普石油天然气勘探及生产精选行业ETF(QDII) | dynamic |
| 159570.SZ | 汇添富国证港股通创新药ETF | core |
| 159682.SZ | 景顺长城创业板50ETF | core |
| 159792.SZ | 富国中证港股通互联网ETF | core |
| 159870.SZ | 鹏华中证细分化工产业主题ETF | core |
| 159887.SZ | 富国中证800银行ETF | core |
| 159915.SZ | 易方达创业板ETF | core+dynamic |
| 159919.SZ | 嘉实沪深300ETF | core |
| 159928.SZ | 汇添富中证主要消费ETF | dynamic |
| 159930.SZ | 汇添富中证能源ETF | dynamic |
| 159941.SZ | 广发纳斯达克100ETF(QDII) | dynamic |
| 159949.SZ | 华安创业板50ETF | core+dynamic |
| 159981.SZ | 建信易盛郑商所能源化工期货ETF | core+dynamic |
| 159995.SZ | 华夏国证半导体芯片ETF | core+dynamic |
| 160723.SZ | 嘉实原油(QDII-LOF-FOF) | core+dynamic |
| 161226.SZ | 国投瑞银白银期货(LOF)-A | core+dynamic |
| 501018.SH | 南方原油(QDII-LOF-FOF)-A | core+dynamic |
| 510050.SH | 华夏上证50ETF | core+dynamic |
| 510300.SH | 华泰柏瑞沪深300ETF | dynamic |
| 510500.SH | 南方中证500ETF | core+dynamic |
| 510880.SH | 华泰柏瑞上证红利ETF | core+dynamic |
| 511360.SH | 海富通中证短融ETF | core+dynamic |
| 511380.SH | 博时中证可转债及可交换债券ETF | core+dynamic |
| 511880.SH | 银华货币ETF-A | core+dynamic |
| 511990.SH | 华宝现金添益货币ETF-A | core+dynamic |
| 512070.SH | 易方达沪深300非银行金融ETF | core+dynamic |
| 512100.SH | 南方中证1000ETF | core+dynamic |
| 512400.SH | 南方中证申万有色金属ETF | core+dynamic |
| 512480.SH | 国联安中证全指半导体产品与设备ETF | core+dynamic |
| 512880.SH | 国泰中证全指证券公司ETF | core+dynamic |
| 512890.SH | 华泰柏瑞中证红利低波动ETF | core+dynamic |
| 513050.SH | 易方达中证海外中国互联网50ETF(QDII) | core+dynamic |
| 513090.SH | 易方达中证香港证券投资主题ETF | core+dynamic |
| 513100.SH | 国泰纳斯达克100ETF(QDII) | core+dynamic |
| 513120.SH | 广发中证香港创新药ETF(QDII) | core+dynamic |
| 513180.SH | 华夏恒生科技ETF(QDII) | core+dynamic |
| 513310.SH | 华泰柏瑞中证韩交所中韩半导体ETF(QDII) | core+dynamic |
| 513330.SH | 华夏恒生互联网科技业ETF(QDII) | core |
| 513400.SH | 鹏华道琼斯工业平均ETF(QDII) | core+dynamic |
| 513500.SH | 博时标普500ETF(QDII) | core+dynamic |
| 513520.SH | 华夏野村日经225ETF(QDII) | core |
| 515070.SH | 华夏中证人工智能主题ETF | dynamic |
| 515180.SH | 易方达中证红利ETF | core+dynamic |
| 515880.SH | 国泰中证全指通信设备ETF | core+dynamic |
| 518850.SH | 华夏黄金ETF | core |
| 518880.SH | 华安易富黄金ETF | dynamic |
| 562500.SH | 华夏中证机器人ETF | core+dynamic |
| 588000.SH | 华夏上证科创板50成份ETF | core+dynamic |

## 2026-06-29 收盘信号

当前为空仓新账户，无持仓、无卖出单。模型选出 Top5，目标等权，每只 `20%`，约 `100,000` 元。

| rank | ts_code | 名称 | score | 目标权重 | 是否动态独有 |
|---:|---|---|---:|---:|---|
| 1 | 159516.SZ | 国泰中证半导体材料设备主题ETF | 6.490088 | 20% | 否 |
| 2 | 513520.SH | 华夏野村日经225ETF(QDII) | 5.680343 | 20% | 否 |
| 3 | 515880.SH | 国泰中证全指通信设备ETF | 4.517297 | 20% | 否 |
| 4 | 512480.SH | 国联安中证全指半导体产品与设备ETF | 0.885975 | 20% | 否 |
| 5 | 159995.SZ | 华夏国证半导体芯片ETF | 0.425400 | 20% | 否 |
| 6 | 159949.SZ | 华安创业板50ETF | 0.332631 | 0% | 否 |
| 7 | 513400.SH | 鹏华道琼斯工业平均ETF(QDII) | 0.326880 | 0% | 否 |
| 8 | 513310.SH | 华泰柏瑞中证韩交所中韩半导体ETF(QDII) | 0.315167 | 0% | 否 |
| 9 | 159682.SZ | 景顺长城创业板50ETF | 0.309550 | 0% | 否 |
| 10 | 159915.SZ | 易方达创业板ETF | 0.302221 | 0% | 否 |
| 11 | 159941.SZ | 广发纳斯达克100ETF(QDII) | 0.192933 | 0% | 是 |
| 12 | 512880.SH | 国泰中证全指证券公司ETF | 0.177265 | 0% | 否 |
| 13 | 513100.SH | 国泰纳斯达克100ETF(QDII) | 0.128344 | 0% | 否 |
| 14 | 513500.SH | 博时标普500ETF(QDII) | 0.095678 | 0% | 否 |
| 15 | 512400.SH | 南方中证申万有色金属ETF | 0.048073 | 0% | 否 |

## 2026-06-30 计划订单

| 动作 | ts_code | 名称 | 目标权重 | 目标金额 | 2026-06-29 收盘价 | 参考股数 | 参考金额 | 备注 |
|---|---|---|---:|---:|---:|---:|---:|---|
| BUY | 159516.SZ | 国泰中证半导体材料设备主题ETF | 20% | 100,000 | 1.921 | 52,000 | 99,892.00 | 明天按实时价格重算手数 |
| BUY | 513520.SH | 华夏野村日经225ETF(QDII) | 20% | 100,000 | 2.487 | 40,200 | 99,977.40 | 明天按实时价格重算手数 |
| BUY | 515880.SH | 国泰中证全指通信设备ETF | 20% | 100,000 | 1.715 | 58,300 | 99,984.50 | 明天按实时价格重算手数 |
| BUY | 512480.SH | 国联安中证全指半导体产品与设备ETF | 20% | 100,000 | 2.909 | 34,300 | 99,778.70 | 明天按实时价格重算手数 |
| BUY | 159995.SZ | 华夏国证半导体芯片ETF | 20% | 100,000 | 3.298 | 30,300 | 99,929.40 | 明天按实时价格重算手数 |

## 明天执行建议

- 因为是第一天建仓，没有卖出单，只有买入单。
- 不建议开盘 09:30 一次性市价打满；优先在 `09:35-10:30` 拆单，或使用前面验证较稳的 `midday_6x` 拆单方式。
- 单只 ETF 目标金额约 10 万，按 100 股整数手下单，实际股数以明天盘口价格重新计算。
- 单笔参与率原则：不要超过执行窗口成交额的 `10%`；如果成交不足，不强行追价，剩余资金保留现金或后续补单。
- 限价原则：以买一/卖一附近小幅让价挂限价单，不用无保护市价单。若高开明显、盘口跳动过大或溢价异常，允许少买或不买。
- 明天成交后再运行 `execute` 记录日线模拟成交；如果是真实模拟盘，应把实际成交价、成交股数、未成交金额手工补入交易日志。

## 复现命令

```bash
cd /Users/jingansun/Desktop/codex/quant
source activate.sh

python runs/etf_loop/etf_loop_paper.py \
  --out-dir outputs/etf_loop_paper/capped_f2_202606_live \
  init --profile capped_f2 --cash 500000 --force

python runs/etf_loop/etf_loop_paper.py \
  --out-dir outputs/etf_loop_paper/capped_f2_202606_live \
  update-data --start 2026-06-29 --end 2026-06-29 --force-basic

python runs/etf_loop/etf_loop_paper.py \
  --out-dir outputs/etf_loop_paper/capped_f2_202606_live \
  generate \
  --signal-date 2026-06-29 \
  --trade-date next \
  --manual-dynamic-pool-file outputs/etf_loop_paper/manual_dynamic_pool_202606.csv \
  --manual-dynamic-pool-mode merge
```

## 输出文件

- 账户文件：`outputs/etf_loop_paper/capped_f2_202606_live/account.json`
- 信号文件：`outputs/etf_loop_paper/capped_f2_202606_live/signals/signal_20260629.csv`
- 原始信号报告：`outputs/etf_loop_paper/capped_f2_202606_live/reports/signal_20260629.md`
- 本交易记录：`outputs/etf_loop_paper/capped_f2_6月_交易.md`
