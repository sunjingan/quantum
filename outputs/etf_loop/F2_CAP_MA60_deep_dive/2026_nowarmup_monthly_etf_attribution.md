# 2026 No-Warmup Monthly ETF Attribution

- tag: `VAL_YR26_NOWARMUP_F2_CAP_MA60`
- portfolio: F2_CAP_MA60 baseline, next-day execution, no signal-date price fallback
- window: 2026-01 to 2026-06
- attribution method: close-to-close daily contribution aligned to engine equity; each ETF contribution = end-of-day market value change + sell proceeds - buy cost

## Monthly Summary

| Month | Return | PnL | Start | End |
|---|---:|---:|---:|---:|
| 2026-01 | +18.99% | 94,969 | 500,000 | 594,969 |
| 2026-02 | -1.78% | -10,598 | 594,969 | 584,371 |
| 2026-03 | +22.05% | 128,829 | 584,371 | 713,200 |
| 2026-04 | +9.27% | 66,103 | 713,200 | 779,303 |
| 2026-05 | +21.00% | 163,681 | 779,303 | 942,984 |
| 2026-06 | -3.81% | -35,914 | 942,984 | 907,070 |

## 2026-01

- Month return: +18.99%
- Month PnL: 94,969
- Start -> End: 500,000 -> 594,969

### Top Losers With Entry/Exit Context

| ETF | Code | Contribution | Buy avg rank | Sell avg rank | Buy near-high | Sell near-low |
|---|---|---:|---:|---:|---:|---:|
| 国联安中证全指半导体产品与设备ETF | 512480.SH | -6,099 | 0.96 | 0.77 | 100% | 0% |
| 华夏上证科创板50成份ETF | 588000.SH | -4,690 | 0.99 | nan | 100% | nan% |
| 国泰中证半导体材料设备主题ETF | 159516.SZ | -3,771 | 1.04 | 0.84 | 100% | 0% |

#### 国联安中证全指半导体产品与设备ETF (512480.SH)
- Month contribution: -6,099
- Buys: 2, Sells: 2

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| BUY | 2026-01-08 | 2026-01-09 | 1.5920 | 62900 | 0.93 | True | False | RANK_IN |
| SELL | 2026-01-13 | 2026-01-14 | 1.5930 | 62900 | 0.80 | False | False | RANK_OUT |
| BUY | 2026-01-28 | 2026-01-29 | 1.7630 | 78800 | 1.00 | True | False | RANK_IN |
| SELL | 2026-01-29 | 2026-01-30 | 1.6860 | 78800 | 0.74 | False | False | RANK_OUT |

#### 华夏上证科创板50成份ETF (588000.SH)
- Month contribution: -4,690
- Buys: 2, Sells: 0

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| BUY | 2026-01-27 | 2026-01-28 | 1.6450 | 71300 | 1.02 | True | False | RANK_IN |
| BUY | 2026-01-28 | 2026-01-29 | 1.6310 | 13900 | 0.96 | True | False | RANK_IN |

#### 国泰中证半导体材料设备主题ETF (159516.SZ)
- Month contribution: -3,771
- Buys: 3, Sells: 3

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| BUY | 2026-01-06 | 2026-01-07 | 1.7420 | 58700 | 1.22 | True | False | RANK_IN |
| SELL | 2026-01-07 | 2026-01-08 | 1.8070 | 58700 | 0.96 | True | False | RANK_OUT |
| BUY | 2026-01-08 | 2026-01-09 | 1.7730 | 56800 | 0.87 | True | False | RANK_IN |
| SELL | 2026-01-13 | 2026-01-14 | 1.7650 | 56800 | 0.83 | True | False | RANK_OUT |
| BUY | 2026-01-16 | 2026-01-19 | 1.9840 | 53100 | 1.04 | True | False | RANK_IN |
| SELL | 2026-01-26 | 2026-01-27 | 1.8520 | 53100 | 0.73 | False | False | STOP_LOSS|RANK_OUT |

### Top Winners

| ETF | Code | Contribution | Buy Trades | Sell Trades | Buy Cost | Sell Proceeds | End MV |
|---|---|---:|---:|---:|---:|---:|---:|
| 国投瑞银白银期货(LOF)-A | 161226.SZ | 68,937 | 1 | 1 | 102,100 | 171,038 | 0 |
| 南方中证申万有色金属ETF | 512400.SH | 15,896 | 2 | 0 | 110,176 | 0 | 126,072 |
| 华泰柏瑞中证韩交所中韩半导体ETF(QDII) | 513310.SH | 14,964 | 5 | 2 | 363,117 | 234,129 | 143,952 |
| 南方中证500ETF | 510500.SH | 7,034 | 5 | 4 | 518,383 | 405,522 | 119,895 |
| 鹏华中证细分化工产业主题ETF | 159870.SZ | 2,353 | 1 | 1 | 99,970 | 102,323 | 0 |
| 华夏国证半导体芯片ETF | 159995.SZ | 760 | 2 | 2 | 232,277 | 233,037 | 0 |
| 易方达沪深300非银行金融ETF | 512070.SH | 609 | 2 | 2 | 203,277 | 203,886 | 0 |
| 永赢中证沪深港黄金产业股票ETF | 517520.SH | -36 | 2 | 1 | 57,474 | 57,438 | 0 |

## 2026-02

- Month return: -1.78%
- Month PnL: -10,598
- Start -> End: 594,969 -> 584,371

### Top Losers With Entry/Exit Context

| ETF | Code | Contribution | Buy avg rank | Sell avg rank | Buy near-high | Sell near-low |
|---|---|---:|---:|---:|---:|---:|
| 南方中证申万有色金属ETF | 512400.SH | -12,635 | nan | 0.20 | nan% | 0% |
| 南方原油(QDII-LOF-FOF)-A | 501018.SH | -5,220 | 0.61 | 0.45 | 0% | 0% |
| 鹏华中证细分化工产业主题ETF | 159870.SZ | -3,931 | 0.63 | 0.24 | 0% | 0% |

#### 南方中证申万有色金属ETF (512400.SH)
- Month contribution: -12,635
- Buys: 0, Sells: 1

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| SELL | 2026-01-30 | 2026-02-02 | 2.1050 | 53900 | 0.20 | False | False | RANK_OUT |

#### 南方原油(QDII-LOF-FOF)-A (501018.SH)
- Month contribution: -5,220
- Buys: 3, Sells: 2

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| BUY | 2026-01-30 | 2026-02-02 | 1.3970 | 60800 | 0.65 | False | False | RANK_IN |
| SELL | 2026-02-02 | 2026-02-03 | 1.2570 | 60800 | 0.34 | False | False | RANK_OUT |
| BUY | 2026-02-09 | 2026-02-10 | 1.3470 | 83200 | 0.49 | False | False | RANK_IN |
| SELL | 2026-02-11 | 2026-02-12 | 1.3790 | 83200 | 0.57 | False | False | RANK_OUT |
| BUY | 2026-02-26 | 2026-02-27 | 1.4300 | 81200 | 0.67 | False | False | RANK_IN |

#### 鹏华中证细分化工产业主题ETF (159870.SZ)
- Month contribution: -3,931
- Buys: 1, Sells: 1

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| BUY | 2026-01-30 | 2026-02-02 | 0.8970 | 129500 | 0.63 | False | False | RANK_IN |
| SELL | 2026-02-02 | 2026-02-03 | 0.8670 | 129500 | 0.24 | False | False | RANK_OUT |

### Top Winners

| ETF | Code | Contribution | Buy Trades | Sell Trades | Buy Cost | Sell Proceeds | End MV |
|---|---|---:|---:|---:|---:|---:|---:|
| 嘉实原油(QDII-LOF-FOF) | 160723.SZ | 7,066 | 3 | 2 | 339,725 | 234,496 | 112,295 |
| 华泰柏瑞中证韩交所中韩半导体ETF(QDII) | 513310.SH | 6,736 | 2 | 3 | 226,352 | 377,040 | 0 |
| 华夏野村日经225ETF(QDII) | 513520.SH | 6,024 | 4 | 2 | 338,292 | 228,978 | 115,338 |
| 华泰柏瑞上证红利ETF | 510880.SH | 1,577 | 3 | 2 | 356,222 | 241,447 | 116,353 |
| 易方达中证红利ETF | 515180.SH | 1,186 | 4 | 3 | 469,903 | 354,549 | 116,539 |
| 博时中证可转债及可交换债券ETF | 511380.SH | 703 | 1 | 1 | 114,324 | 115,027 | 0 |
| 建信易盛郑商所能源化工期货ETF | 159981.SZ | 393 | 1 | 1 | 112,285 | 112,677 | 0 |
| 鹏华道琼斯工业平均ETF(QDII) | 513400.SH | 341 | 2 | 1 | 115,685 | 116,026 | 0 |

## 2026-03

- Month return: +22.05%
- Month PnL: 128,829
- Start -> End: 584,371 -> 713,200

### Top Losers With Entry/Exit Context

| ETF | Code | Contribution | Buy avg rank | Sell avg rank | Buy near-high | Sell near-low |
|---|---|---:|---:|---:|---:|---:|
| 华夏野村日经225ETF(QDII) | 513520.SH | -10,919 | 0.88 | 0.32 | 100% | 0% |
| 富国中证800银行ETF | 159887.SZ | -5,533 | 0.72 | 0.28 | 50% | 50% |
| 华泰柏瑞中证红利低波动ETF | 512890.SH | -2,974 | 0.84 | 0.51 | 50% | 50% |

#### 华夏野村日经225ETF(QDII) (513520.SH)
- Month contribution: -10,919
- Buys: 1, Sells: 1

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| BUY | 2026-03-02 | 2026-03-03 | 2.1060 | 3900 | 0.88 | True | False | RANK_IN |
| SELL | 2026-03-03 | 2026-03-04 | 1.9390 | 58100 | 0.32 | False | False | STOP_LOSS|RANK_OUT |

#### 富国中证800银行ETF (159887.SZ)
- Month contribution: -5,533
- Buys: 2, Sells: 2

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| BUY | 2026-03-17 | 2026-03-18 | 1.3100 | 106300 | 0.98 | True | False | RANK_IN |
| SELL | 2026-03-23 | 2026-03-24 | 1.2590 | 106300 | 0.10 | False | True | ATR_STOP|RANK_OUT |
| BUY | 2026-03-24 | 2026-03-25 | 1.2800 | 111300 | 0.47 | False | False | RANK_IN |
| SELL | 2026-03-27 | 2026-03-30 | 1.2800 | 111300 | 0.47 | False | False | RANK_OUT |

#### 华泰柏瑞中证红利低波动ETF (512890.SH)
- Month contribution: -2,974
- Buys: 2, Sells: 2

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| BUY | 2026-03-10 | 2026-03-11 | 1.1840 | 111000 | 0.74 | False | False | RANK_IN |
| SELL | 2026-03-12 | 2026-03-13 | 1.2010 | 111000 | 0.97 | True | False | RANK_OUT |
| BUY | 2026-03-16 | 2026-03-17 | 1.2030 | 113200 | 0.95 | True | False | RANK_IN |
| SELL | 2026-03-23 | 2026-03-24 | 1.1610 | 113200 | 0.06 | False | True | ATR_STOP|RANK_OUT |

### Top Winners

| ETF | Code | Contribution | Buy Trades | Sell Trades | Buy Cost | Sell Proceeds | End MV |
|---|---|---:|---:|---:|---:|---:|---:|
| 南方原油(QDII-LOF-FOF)-A | 501018.SH | 53,845 | 2 | 3 | 271,872 | 442,564 | 0 |
| 嘉实原油(QDII-LOF-FOF) | 160723.SZ | 53,485 | 3 | 3 | 419,726 | 443,293 | 142,213 |
| 华泰柏瑞中证韩交所中韩半导体ETF(QDII) | 513310.SH | 23,071 | 2 | 2 | 245,127 | 268,199 | 0 |
| 建信易盛郑商所能源化工期货ETF | 159981.SZ | 18,860 | 5 | 3 | 541,018 | 418,322 | 141,556 |
| 汇添富国证港股通创新药ETF | 159570.SZ | 2,578 | 1 | 0 | 142,751 | 0 | 145,329 |
| 华泰柏瑞上证红利ETF | 510880.SH | 931 | 3 | 2 | 152,515 | 269,799 | 0 |
| 易方达中证红利ETF | 515180.SH | 626 | 3 | 3 | 258,580 | 375,745 | 0 |
| 海富通中证短融ETF | 511360.SH | -20 | 2 | 1 | 271,753 | 135,825 | 135,908 |

## 2026-04

- Month return: +9.27%
- Month PnL: 66,103
- Start -> End: 713,200 -> 779,303

### Top Losers With Entry/Exit Context

| ETF | Code | Contribution | Buy avg rank | Sell avg rank | Buy near-high | Sell near-low |
|---|---|---:|---:|---:|---:|---:|
| 南方中证申万有色金属ETF | 512400.SH | -6,805 | 0.99 | 0.63 | 100% | 0% |
| 建信易盛郑商所能源化工期货ETF | 159981.SZ | -3,524 | 0.61 | 0.59 | 0% | 0% |
| 易方达创业板ETF | 159915.SZ | -3,367 | 0.95 | 0.87 | 100% | 0% |

#### 南方中证申万有色金属ETF (512400.SH)
- Month contribution: -6,805
- Buys: 1, Sells: 1

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| BUY | 2026-04-22 | 2026-04-23 | 2.1780 | 71000 | 0.99 | True | False | RANK_IN |
| SELL | 2026-04-23 | 2026-04-24 | 2.0830 | 71000 | 0.63 | False | False | RANK_OUT |

#### 建信易盛郑商所能源化工期货ETF (159981.SZ)
- Month contribution: -3,524
- Buys: 1, Sells: 2

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| SELL | 2026-04-01 | 2026-04-02 | 1.6740 | 82300 | 0.71 | False | False | STOP_LOSS|RANK_OUT |
| BUY | 2026-04-07 | 2026-04-08 | 1.6640 | 86800 | 0.61 | False | False | RANK_IN |
| SELL | 2026-04-08 | 2026-04-09 | 1.6680 | 86800 | 0.46 | False | False | RANK_OUT |

#### 易方达创业板ETF (159915.SZ)
- Month contribution: -3,367
- Buys: 3, Sells: 2

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| BUY | 2026-04-15 | 2026-04-16 | 3.5220 | 41500 | 0.93 | True | False | RANK_IN |
| SELL | 2026-04-16 | 2026-04-17 | 3.6380 | 41500 | 1.03 | True | False | RANK_OUT |
| BUY | 2026-04-22 | 2026-04-23 | 3.7690 | 41000 | 1.02 | True | False | RANK_IN |
| BUY | 2026-04-23 | 2026-04-24 | 3.6890 | 4900 | 0.89 | True | False | RANK_IN |
| SELL | 2026-04-28 | 2026-04-29 | 3.5850 | 45900 | 0.72 | False | False | RANK_OUT |

### Top Winners

| ETF | Code | Contribution | Buy Trades | Sell Trades | Buy Cost | Sell Proceeds | End MV |
|---|---|---:|---:|---:|---:|---:|---:|
| 国泰中证全指通信设备ETF | 515880.SH | 20,921 | 2 | 1 | 307,012 | 168,570 | 159,363 |
| 国联安中证全指半导体产品与设备ETF | 512480.SH | 13,682 | 2 | 0 | 172,561 | 0 | 186,243 |
| 嘉实上证科创板芯片ETF | 588200.SH | 9,253 | 1 | 0 | 74,431 | 0 | 83,685 |
| 汇添富国证港股通创新药ETF | 159570.SZ | 9,111 | 1 | 2 | 150,504 | 304,945 | 0 |
| 华夏国证半导体芯片ETF | 159995.SZ | 7,165 | 1 | 0 | 170,491 | 0 | 177,655 |
| 嘉实原油(QDII-LOF-FOF) | 160723.SZ | 6,350 | 1 | 2 | 133,891 | 282,454 | 0 |
| 国泰中证半导体材料设备主题ETF | 159516.SZ | 4,941 | 2 | 1 | 319,040 | 151,925 | 172,057 |
| 华安创业板50ETF | 159949.SZ | 4,578 | 3 | 2 | 316,853 | 321,430 | 0 |

## 2026-05

- Month return: +21.00%
- Month PnL: 163,681
- Start -> End: 779,303 -> 942,984

### Top Losers With Entry/Exit Context

| ETF | Code | Contribution | Buy avg rank | Sell avg rank | Buy near-high | Sell near-low |
|---|---|---:|---:|---:|---:|---:|

### Top Winners

| ETF | Code | Contribution | Buy Trades | Sell Trades | Buy Cost | Sell Proceeds | End MV |
|---|---|---:|---:|---:|---:|---:|---:|
| 华夏国证半导体芯片ETF | 159995.SZ | 35,819 | 0 | 0 | 0 | 0 | 213,474 |
| 华泰柏瑞中证韩交所中韩半导体ETF(QDII) | 513310.SH | 32,748 | 4 | 3 | 594,652 | 627,400 | 0 |
| 华夏上证科创板50成份ETF | 588000.SH | 22,955 | 5 | 3 | 704,937 | 514,000 | 213,892 |
| 国泰中证半导体材料设备主题ETF | 159516.SZ | 22,403 | 2 | 3 | 425,793 | 620,253 | 0 |
| 国联安中证全指半导体产品与设备ETF | 512480.SH | 16,970 | 2 | 1 | 233,143 | 219,921 | 216,434 |
| 景顺长城创业板50ETF | 159682.SZ | 9,236 | 3 | 3 | 574,587 | 583,823 | 0 |
| 国泰纳斯达克100ETF(QDII) | 513100.SH | 8,500 | 1 | 1 | 191,474 | 199,975 | 0 |
| 易方达创业板ETF | 159915.SZ | 6,578 | 1 | 1 | 191,174 | 197,752 | 0 |

## 2026-06

- Month return: -3.81%
- Month PnL: -35,914
- Start -> End: 942,984 -> 907,070

### Top Losers With Entry/Exit Context

| ETF | Code | Contribution | Buy avg rank | Sell avg rank | Buy near-high | Sell near-low |
|---|---|---:|---:|---:|---:|---:|
| 华泰柏瑞中证韩交所中韩半导体ETF(QDII) | 513310.SH | -24,819 | 0.61 | 0.03 | 0% | 100% |
| 华夏国证半导体芯片ETF | 159995.SZ | -16,693 | 0.54 | 0.27 | 0% | 50% |
| 国泰纳斯达克100ETF(QDII) | 513100.SH | -11,002 | 0.90 | 0.49 | 75% | 0% |

#### 华泰柏瑞中证韩交所中韩半导体ETF(QDII) (513310.SH)
- Month contribution: -24,819
- Buys: 2, Sells: 1

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| BUY | 2026-06-03 | 2026-06-04 | 6.1500 | 30600 | 0.76 | False | False | RANK_IN |
| BUY | 2026-06-04 | 2026-06-05 | 5.7662 | 1400 | 0.47 | False | False | RANK_IN |
| SELL | 2026-06-05 | 2026-06-08 | 5.3599 | 32000 | 0.03 | False | True | STOP_LOSS|RANK_OUT |

#### 华夏国证半导体芯片ETF (159995.SZ)
- Month contribution: -16,693
- Buys: 1, Sells: 2

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| SELL | 2026-05-29 | 2026-06-01 | 2.4849 | 85700 | 0.68 | False | False | RANK_OUT |
| BUY | 2026-06-04 | 2026-06-05 | 2.4710 | 74700 | 0.54 | False | False | RANK_IN |
| SELL | 2026-06-05 | 2026-06-08 | 2.2559 | 74700 | -0.13 | False | True | RANK_OUT |

#### 国泰纳斯达克100ETF(QDII) (513100.SH)
- Month contribution: -11,002
- Buys: 4, Sells: 1

| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| BUY | 2026-05-29 | 2026-06-01 | 2.2731 | 75600 | 1.00 | True | False | RANK_IN |
| BUY | 2026-06-01 | 2026-06-02 | 2.3551 | 3200 | 0.98 | True | False | RANK_IN |
| BUY | 2026-06-03 | 2026-06-04 | 2.3099 | 2700 | 0.83 | True | False | RANK_IN |
| SELL | 2026-06-04 | 2026-06-05 | 2.2020 | 81500 | 0.49 | False | False | RANK_OUT |
| BUY | 2026-06-18 | 2026-06-22 | 2.3107 | 77700 | 0.78 | False | False | RANK_IN |

### Top Winners

| ETF | Code | Contribution | Buy Trades | Sell Trades | Buy Cost | Sell Proceeds | End MV |
|---|---|---:|---:|---:|---:|---:|---:|
| 国泰中证半导体材料设备主题ETF | 159516.SZ | 17,754 | 3 | 1 | 335,424 | 159,820 | 193,358 |
| 华夏野村日经225ETF(QDII) | 513520.SH | 15,646 | 3 | 2 | 517,565 | 355,707 | 177,504 |
| 景顺长城创业板50ETF | 159682.SZ | 2,805 | 1 | 1 | 188,054 | 190,859 | 0 |
| 华安创业板50ETF | 159949.SZ | 2,311 | 1 | 1 | 188,187 | 190,497 | 0 |
| 国泰中证全指通信设备ETF | 515880.SH | 1,791 | 2 | 2 | 349,751 | 369,410 | 186,836 |
| 鹏华道琼斯工业平均ETF(QDII) | 513400.SH | 1,720 | 3 | 2 | 512,145 | 342,914 | 170,951 |
| 银华货币ETF-A | 511880.SH | -64 | 1 | 1 | 172,879 | 172,815 | 0 |
| 富国中证800银行ETF | 159887.SZ | -97 | 1 | 1 | 173,091 | 172,994 | 0 |

## 2026-06 Round Trips

| ETF | Buy signal | Buy exec | Buy px | Buy rank20 | Sell signal | Sell exec | Sell px | Sell rank20 | Shares | Hold days | Gross PnL | Net PnL | Buy high? | Sell low? | Sell reason |
|---|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| 华夏国证半导体芯片ETF | 2026-04-27 | 2026-04-28 | 1.9890 | 0.96 | 2026-05-29 | 2026-06-01 | 2.4849 | 0.68 | 85700 | 34 | 42,502 | 42,425 | True | False | RANK_OUT |
| 国联安中证全指半导体产品与设备ETF | 2026-05-26 | 2026-05-27 | 2.3290 | 0.97 | 2026-05-29 | 2026-06-01 | 2.1530 | 0.68 | 97500 | 5 | -17,163 | -17,250 | True | False | STOP_LOSS|RANK_OUT |
| 国联安中证全指半导体产品与设备ETF | 2026-05-27 | 2026-05-28 | 2.2290 | 0.81 | 2026-05-29 | 2026-06-01 | 2.1530 | 0.68 | 2700 | 4 | -205 | -208 | True | False | STOP_LOSS|RANK_OUT |
| 华夏上证科创板50成份ETF | 2026-05-27 | 2026-05-28 | 1.8930 | 0.76 | 2026-05-29 | 2026-06-01 | 1.8409 | 0.63 | 116000 | 4 | -6,039 | -6,125 | False | False | RANK_OUT |
| 嘉实上证科创板芯片ETF | 2026-05-26 | 2026-05-27 | 3.8400 | 0.94 | 2026-05-29 | 2026-06-01 | 3.5804 | 0.68 | 26300 | 5 | -6,828 | -6,867 | True | False | STOP_LOSS|RANK_OUT |
| 国泰中证全指通信设备ETF | 2026-05-28 | 2026-05-29 | 4.8647 | 1.01 | 2026-06-01 | 2026-06-02 | 4.6063 | 0.72 | 42900 | 4 | -11,083 | -11,164 | True | False | STOP_LOSS|RANK_OUT |
| 博时标普500ETF(QDII) | 2026-06-01 | 2026-06-02 | 2.6362 | 1.05 | 2026-06-02 | 2026-06-03 | 2.6230 | 0.99 | 70400 | 1 | -925 | -999 | True | False | RANK_OUT |
| 易方达创业板ETF | 2026-05-29 | 2026-06-01 | 4.0469 | 0.80 | 2026-06-03 | 2026-06-04 | 4.0739 | 0.79 | 46500 | 3 | 1,253 | 1,177 | False | False | RANK_OUT |
| 华夏野村日经225ETF(QDII) | 2026-06-02 | 2026-06-03 | 2.3911 | 1.19 | 2026-06-03 | 2026-06-04 | 2.3351 | 0.86 | 78800 | 1 | -4,418 | -4,492 | True | False | RANK_OUT |
| 景顺长城创业板50ETF | 2026-05-29 | 2026-06-01 | 1.9049 | 0.82 | 2026-06-04 | 2026-06-05 | 1.9341 | 0.85 | 98700 | 4 | 2,881 | 2,805 | True | False | RANK_OUT |
| 华安创业板50ETF | 2026-05-29 | 2026-06-01 | 1.9640 | 0.84 | 2026-06-04 | 2026-06-05 | 1.9889 | 0.86 | 95800 | 4 | 2,386 | 2,311 | True | False | RANK_OUT |
| 国泰纳斯达克100ETF(QDII) | 2026-05-29 | 2026-06-01 | 2.2731 | 1.00 | 2026-06-04 | 2026-06-05 | 2.2020 | 0.49 | 75600 | 4 | -5,373 | -5,441 | True | False | RANK_OUT |
| 国泰纳斯达克100ETF(QDII) | 2026-06-01 | 2026-06-02 | 2.3551 | 0.98 | 2026-06-04 | 2026-06-05 | 2.2020 | 0.49 | 3200 | 3 | -490 | -493 | True | False | RANK_OUT |
| 国泰纳斯达克100ETF(QDII) | 2026-06-03 | 2026-06-04 | 2.3099 | 0.83 | 2026-06-04 | 2026-06-05 | 2.2020 | 0.49 | 2700 | 1 | -291 | -294 | True | False | RANK_OUT |
| 博时标普500ETF(QDII) | 2026-06-03 | 2026-06-04 | 2.5641 | 0.68 | 2026-06-04 | 2026-06-05 | 2.5692 | 0.71 | 70000 | 1 | 354 | 282 | False | False | RANK_OUT |
| 华夏国证半导体芯片ETF | 2026-06-04 | 2026-06-05 | 2.4710 | 0.54 | 2026-06-05 | 2026-06-08 | 2.2559 | -0.13 | 74700 | 3 | -16,064 | -16,135 | False | True | RANK_OUT |
| 国联安中证全指半导体产品与设备ETF | 2026-06-04 | 2026-06-05 | 2.1501 | 0.56 | 2026-06-05 | 2026-06-08 | 1.9861 | -0.10 | 85800 | 3 | -14,070 | -14,141 | False | True | RANK_OUT |
| 华泰柏瑞中证韩交所中韩半导体ETF(QDII) | 2026-06-03 | 2026-06-04 | 6.1500 | 0.76 | 2026-06-05 | 2026-06-08 | 5.3599 | 0.03 | 30600 | 4 | -24,177 | -24,247 | False | True | STOP_LOSS|RANK_OUT |
| 华泰柏瑞中证韩交所中韩半导体ETF(QDII) | 2026-06-04 | 2026-06-05 | 5.7662 | 0.47 | 2026-06-05 | 2026-06-08 | 5.3599 | 0.03 | 1400 | 3 | -569 | -572 | False | True | STOP_LOSS|RANK_OUT |
| 易方达创业板ETF | 2026-06-04 | 2026-06-05 | 4.0829 | 0.82 | 2026-06-08 | 2026-06-09 | 3.8770 | 0.16 | 45200 | 4 | -9,306 | -9,378 | True | True | STOP_LOSS|ATR_STOP|RANK_OUT |
| 鹏华道琼斯工业平均ETF(QDII) | 2026-06-05 | 2026-06-08 | 1.2602 | 0.59 | 2026-06-08 | 2026-06-09 | 1.2572 | 0.54 | 137300 | 1 | -407 | -476 | False | False | RANK_OUT |
| 博时标普500ETF(QDII) | 2026-06-05 | 2026-06-08 | 2.4993 | 0.35 | 2026-06-08 | 2026-06-09 | 2.5222 | 0.47 | 69200 | 1 | 1,590 | 1,520 | False | False | RANK_OUT |
| 华夏野村日经225ETF(QDII) | 2026-06-05 | 2026-06-08 | 2.1731 | 0.40 | 2026-06-08 | 2026-06-09 | 2.2721 | 0.68 | 75600 | 1 | 7,491 | 7,423 | False | False | RANK_OUT |
| 国泰中证全指通信设备ETF | 2026-06-04 | 2026-06-05 | 5.0918 | 0.93 | 2026-06-08 | 2026-06-09 | 4.8966 | 0.69 | 35100 | 4 | -6,851 | -6,921 | True | False | STOP_LOSS|RANK_OUT |
| 建信易盛郑商所能源化工期货ETF | 2026-06-08 | 2026-06-09 | 1.6589 | 0.73 | 2026-06-09 | 2026-06-10 | 1.6369 | 0.53 | 104300 | 1 | -2,298 | -2,367 | False | False | RANK_OUT |
| 嘉实原油(QDII-LOF-FOF) | 2026-06-08 | 2026-06-09 | 2.2962 | 0.65 | 2026-06-09 | 2026-06-10 | 2.2373 | 0.45 | 75400 | 1 | -4,445 | -4,513 | False | False | RANK_OUT |
| 博时标普500ETF(QDII) | 2026-06-09 | 2026-06-10 | 2.5222 | 0.47 | 2026-06-10 | 2026-06-11 | 2.4821 | 0.26 | 67600 | 1 | -2,711 | -2,779 | False | False | RANK_OUT |
| 鹏华道琼斯工业平均ETF(QDII) | 2026-06-10 | 2026-06-11 | 1.2401 | 0.31 | 2026-06-11 | 2026-06-12 | 1.2592 | 0.57 | 135300 | 1 | 2,573 | 2,505 | False | False | RANK_OUT |
| 国泰中证半导体材料设备主题ETF | 2026-06-11 | 2026-06-12 | 2.8561 | 1.32 | 2026-06-12 | 2026-06-15 | 2.6821 | 0.92 | 59600 | 3 | -10,374 | -10,440 | True | False | STOP_LOSS |
| 华泰柏瑞上证红利ETF | 2026-06-09 | 2026-06-10 | 3.4265 | 0.69 | 2026-06-15 | 2026-06-16 | 3.3898 | 0.49 | 50200 | 6 | -1,843 | -1,911 | False | False | RANK_OUT |
| 海富通中证短融ETF | 2026-06-08 | 2026-06-09 | 113.5595 | 0.98 | 2026-06-16 | 2026-06-17 | 113.5367 | 0.69 | 1500 | 8 | -34 | -102 | True | False | RANK_OUT |
| 银华货币ETF-A | 2026-06-08 | 2026-06-09 | 101.6733 | 0.88 | 2026-06-16 | 2026-06-17 | 101.6763 | 0.84 | 1700 | 8 | 5 | -64 | True | False | RANK_OUT |
| 富国中证800银行ETF | 2026-06-08 | 2026-06-09 | 1.2800 | 0.84 | 2026-06-17 | 2026-06-18 | 1.2798 | 0.43 | 135200 | 9 | -28 | -97 | True | False | RANK_OUT |
| 国联安中证全指半导体产品与设备ETF | 2026-06-17 | 2026-06-18 | 2.3840 | 0.99 | 2026-06-18 | 2026-06-22 | 2.5119 | 1.06 | 72900 | 4 | 9,328 | 9,257 | True | False | RANK_OUT |