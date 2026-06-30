# ETF Loop 本地轻量模拟盘

本工具用于在本地跑 ETF 轮动策略模拟盘，不依赖 Qlib online serving。数据更新仍通过 Tushare API 写入本地缓存，信号生成只使用信号日及以前数据，交易执行只使用成交日精确开盘价。

## 环境

```bash
cd /Users/jingansun/Desktop/codex/quant
source activate.sh
```

默认读取：

- Tushare token: `config/tushare_token.txt`
- 数据缓存: `data/tushare_cache`
- 模拟盘输出: `outputs/etf_loop_paper`

## 初始化账户

```bash
python runs/etf_loop/etf_loop_paper.py init --profile capped_f2 --cash 500000
```

如果要重建账户：

```bash
python runs/etf_loop/etf_loop_paper.py init --profile capped_f2 --cash 500000 --force
```

`--force` 会覆盖 `account.json`，并清理该模拟盘目录下的旧 `orders.csv`、`trades.csv`、`nav.csv`、`signals/*.csv`、`reports/*.md`，避免新账户混入旧日志。

可选 profile：

- `static_f2`: 只用 F2_v3 精选池。
- `static_f2_orig38`: F2_v3 + 原始 38 只静态池。
- `old_union_f2`: F2_v3 与 G2 PIT 动态池简单并集。
- `old_union_f2_orig38`: F2_v3 + 原始 38 只静态池与 G2 PIT 动态池简单并集。
- `capped_f2`: 当前推荐，F2_v3 为核心池，G2 PIT 动态池最多 1 个席位、最多 10% 权重，并带过热惩罚。
- `capped_f2_orig38`: F2_v3 + 原始 38 只为核心池，G2 PIT 动态池最多 1 个席位、最多 20% 权重，并带过热惩罚。

## 每日流程

1. 收盘后更新 Tushare 数据：

```bash
python runs/etf_loop/etf_loop_paper.py update-data --start 2026-06-26 --end 2026-06-26
```

2. 用信号日收盘后可见数据生成下一交易日计划订单：

```bash
python runs/etf_loop/etf_loop_paper.py generate --signal-date latest --trade-date next
```

如果要在生成信号时主动拉取信号日行情：

```bash
python runs/etf_loop/etf_loop_paper.py generate --signal-date 2026-06-26 --trade-date next --fetch-signal
```

如果本月动态池需要加入人工推荐池，可以在生成信号时传入 `--manual-dynamic-pool-file`。默认 `merge` 表示“PIT 月度动态池 + 手工池”取并集，只影响当前信号月份的模拟盘信号，不会改历史回测文件。

```bash
python runs/etf_loop/etf_loop_paper.py generate \
  --signal-date 2026-06-26 \
  --trade-date next \
  --manual-dynamic-pool-file outputs/etf_loop_paper/manual_dynamic_pool_202606.csv \
  --manual-dynamic-pool-mode merge
```

也可以直接用逗号传入代码，支持 `588000`、`588000.SH`、`588000.XSHG` 三种格式：

```bash
python runs/etf_loop/etf_loop_paper.py generate \
  --signal-date 2026-06-26 \
  --trade-date next \
  --manual-dynamic-pool 588000,159995,515070,562500,512880,512890,159928,159941,518880,159930 \
  --manual-dynamic-pool-mode merge
```

如果想完全不用 PIT 自动池，只采用这 10 只作为本月动态池，把 `merge` 改成 `replace`。

3. 下一交易日开盘后执行模拟成交：

```bash
python runs/etf_loop/etf_loop_paper.py execute --trade-date 2026-06-29 --fetch-trade
```

`--fetch-trade` 会先通过 Tushare 拉取成交日行情。成交只用成交日开盘价；如果某 ETF 缺少成交日开盘价，订单会跳过，不会回退到信号日收盘价。

4. 查看账户状态：

```bash
python runs/etf_loop/etf_loop_paper.py status --date latest
```

## 一键日常命令

下面命令适合在收盘后执行，只负责更新数据并生成下一交易日订单，不会执行成交：

```bash
python runs/etf_loop/etf_loop_paper.py run-day --start 2026-06-26 --end 2026-06-26 --signal-date 2026-06-26 --trade-date next
```

带手工动态池的一键命令：

```bash
python runs/etf_loop/etf_loop_paper.py run-day \
  --start 2026-06-26 \
  --end 2026-06-26 \
  --signal-date 2026-06-26 \
  --trade-date next \
  --manual-dynamic-pool-file outputs/etf_loop_paper/manual_dynamic_pool_202606.csv \
  --manual-dynamic-pool-mode merge
```

## 第一天模拟盘示例

假设 `2026-06-26` 是上一个交易日收盘，`2026-06-29` 是第一个模拟交易日，初始资金 50 万，采用当前候选 `capped_f2`：

```bash
cd /Users/jingansun/Desktop/codex/quant
source activate.sh

python runs/etf_loop/etf_loop_paper.py init --profile capped_f2 --cash 500000 --force

python runs/etf_loop/etf_loop_paper.py update-data --start 2026-06-26 --end 2026-06-26

python runs/etf_loop/etf_loop_paper.py generate \
  --signal-date 2026-06-26 \
  --trade-date 2026-06-29 \
  --manual-dynamic-pool-file outputs/etf_loop_paper/manual_dynamic_pool_202606.csv \
  --manual-dynamic-pool-mode merge
```

生成后先看：

```bash
cat outputs/etf_loop_paper/reports/signal_20260626.md
```

报告会列出：

- `manual_dynamic_pool_size`: 人工池数量。
- `original_pit_dynamic_pool_size`: 原 PIT 月度动态池数量。
- `effective_dynamic_pool_size`: 合并/替换后的本月动态池数量。
- `targets`: 明日目标持仓。
- `Orders`: 明日计划卖出/买入。

如果只是影子盘，今天实际不下单，可以不运行 `execute`，只把 `signals/` 和 `orders.csv` 作为当时信号留档。如果要用日线开盘价做轻量模拟成交，在当天日线数据可取到后执行：

```bash
python runs/etf_loop/etf_loop_paper.py execute --trade-date 2026-06-29 --fetch-trade
python runs/etf_loop/etf_loop_paper.py status --date 2026-06-29
```

实盘/严肃模拟盘不建议简单等价为“开盘一次性打满”。更稳妥的操作是：先卖出不在目标持仓内的 ETF，再按目标权重买入；单笔订单不超过执行窗口成交额的 10%，未成交部分保留现金或分批补单；优先使用 `09:35-10:30 VWAP/TWAP` 或 `midday_6x` 这类拆单执行，而不是追求一次性满仓成交。当前脚本的 `execute` 是日线开盘价轻量模拟，不是分钟级撮合引擎。

## 输出文件

- `outputs/etf_loop_paper/account.json`: 当前现金、持仓、待执行订单。
- `outputs/etf_loop_paper/orders.csv`: 每次信号生成的订单快照。
- `outputs/etf_loop_paper/trades.csv`: 实际模拟成交记录。
- `outputs/etf_loop_paper/nav.csv`: 每次执行后的现金、市值、组合净值。
- `outputs/etf_loop_paper/signals/signal_YYYYMMDD.csv`: 信号日排名、得分、目标权重、动态池标记。
- `outputs/etf_loop_paper/reports/`: 每次信号和执行的 Markdown 摘要。
- `outputs/etf_loop_paper/manual_dynamic_pool_202606.csv`: 2026-06 示例手工动态池。

## 策略与成交规则

- 选 ETF 逻辑复用 `strategies/etf_loop_strategy.py` 与 `strategies/etf_loop_engine.py`。
- 默认持仓数为 5。
- 卖出先于买入执行，释放现金后再按目标权重买入。
- 卖出触发条件包括排名出局、固定止损、ATR 止损。
- 买入按目标权重与当前持仓差额下单，并套用原回测引擎里的手续费、滑点、最低成交金额、流动性约束。
- 买入卖出都必须有成交日精确开盘价；缺失则跳过。

## 无未来函数边界

- 信号生成的行情窗口截止到 `signal_date`。
- `generate` 不会主动获取成交日行情，除非用户错误地把成交日传成信号日，这一点由日期参数控制。
- `execute` 才读取 `trade_date` 行情，且只用于模拟成交与成交后估值。
- 禁止任何价格 fallback 到信号日收盘价成交；成交日无开盘价时订单状态为 `SKIPPED_NO_OPEN` 或 `SKIPPED_NO_OPEN_OR_LIQUIDITY`。
- 动态池使用 PIT 文件 `data/tushare_cache/sector_prosperity/etf_pool_G2_PIT_monthly.pkl`，按信号日所在月份选择当时可见池子。

## 本地复现测试

不污染正式输出目录的测试命令：

```bash
python runs/etf_loop/etf_loop_paper.py --out-dir /private/tmp/etf_loop_paper_test init --profile capped_f2 --cash 500000 --force
python runs/etf_loop/etf_loop_paper.py --out-dir /private/tmp/etf_loop_paper_test generate --signal-date 2026-06-19 --trade-date 2026-06-22
python runs/etf_loop/etf_loop_paper.py --out-dir /private/tmp/etf_loop_paper_test execute --trade-date 2026-06-22
python runs/etf_loop/etf_loop_paper.py --out-dir /private/tmp/etf_loop_paper_test status --date 2026-06-22
```

该测试使用 `2026-06-19` 收盘信号，`2026-06-22` 开盘成交，验证信号日和成交日严格分离。
