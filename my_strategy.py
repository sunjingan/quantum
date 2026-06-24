"""
我的第一个 Qlib 策略 — LightGBM 选股
用法:  source activate.sh && python my_strategy.py

Qlib 跑一个策略的完整流程:
  1. 初始化 Qlib (连接数据)
  2. 定义数据处理器 (Alpha158 = 158 个量价因子)
  3. 构建数据集 (DatasetH 自动划分训练/测试)
  4. 训练模型 (LightGBM)
  5. 预测 + 回测评估

这里有两条路:
  A) Python 代码方式 (本文件) — 灵活，适合探索和研究
  B) YAML + qrun 方式 — 适合正式实验，自动记录到 MLflow
      用法: source activate.sh && qrun my_strategy.yaml
"""
import multiprocessing
import os
from pathlib import Path

# macOS: Python 3.8+ 默认用 spawn 启动子进程，Qlib 的数据加载需要 fork
multiprocessing.set_start_method("fork")

BASE_DIR = Path(__file__).resolve().parent
PROVIDER_URI = Path(os.environ.get("QLIB_PROVIDER_URI", BASE_DIR / "data" / "a_share_qlib"))
DATA_START = "2000-01-04"
DATA_END = "2026-06-22"
MODEL_END = DATA_END
TRAIN_END = "2018-12-28"
TEST_START = "2019-01-02"
MARKET = "all_a"
BENCHMARK = "sh000300"

# MLflow 4.x 默认阻止继续写 ./mlruns 文件存储；本地研究环境显式允许即可。
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".matplotlib"))

from lazy_tushare_loader import LazyTushareLoader

if os.environ.get("QLIB_LAZY_TUSHARE", "1") != "0":
    LazyTushareLoader.for_project(BASE_DIR, PROVIDER_URI).ensure(
        instruments=MARKET,
        start_time=DATA_START,
        end_time=DATA_END,
        benchmark=BENCHMARK,
    )

import qlib
from qlib.utils import init_instance_by_config
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord, SigAnaRecord
from qlib.utils import flatten_dict

# ─── 第 1 步: 初始化 Qlib（连接数据） ───
qlib.init(
    provider_uri=str(PROVIDER_URI),
    region="cn",
)

# ─── 第 2-3 步: 数据集配置 ───
# Alpha158: Qlib 内置的 158 个 A 股量价因子（动量、波动率、换手率等）
dataset_config = {
    "class": "DatasetH",
    "module_path": "qlib.data.dataset",
    "kwargs": {
        "handler": {
            "class": "Alpha158",
            "module_path": "qlib.contrib.data.handler",
            "kwargs": {
                "start_time": DATA_START,
                "end_time": MODEL_END,
                "fit_start_time": DATA_START,
                "fit_end_time": TRAIN_END,
                "instruments": MARKET,
            },
        },
        "segments": {
            "train": (DATA_START, TRAIN_END),
            "test": (TEST_START, MODEL_END),
        },
    },
}

# ─── 第 4 步: 模型配置 ───
model_config = {
    "class": "LGBModel",
    "module_path": "qlib.contrib.model.gbdt",
    "kwargs": {
        "loss": "mse",
        "learning_rate": 0.1,
        "max_depth": 6,
        "num_leaves": 100,
        "num_threads": 1,
    },
}

# ─── 回测配置 ───
port_analysis_config = {
    "executor": {
        "class": "SimulatorExecutor",
        "module_path": "qlib.backtest.executor",
        "kwargs": {"time_per_step": "day", "generate_portfolio_metrics": True},
    },
    "strategy": {
        "class": "TopkDropoutStrategy",
        "module_path": "qlib.contrib.strategy.signal_strategy",
        "kwargs": {
            "signal": "<PRED>",  # 占位符，后面会替换为实际预测
            "topk": 5,
            "n_drop": 1,         # 每次换仓最多替换 1 只
        },
    },
    "backtest": {
        "start_time": TEST_START,
        "end_time": MODEL_END,
        "account": 100_000_000,  # 初始资金 1 亿
        "benchmark": BENCHMARK,
        "exchange_kwargs": {
            "freq": "day",
            "limit_threshold": 0.095,
            "deal_price": "close",
            "open_cost": 0.0005,   # 买入费率
            "close_cost": 0.0015,  # 卖出费率
            "min_cost": 5,         # 最低佣金
        },
    },
}

# ─── 第 5 步: 训练 + 预测 + 回测 ───
if __name__ == "__main__":
    print(f"Qlib 数据路径: {PROVIDER_URI}")
    dataset = init_instance_by_config(dataset_config)
    model = init_instance_by_config(model_config)

    # 查看数据
    train_data = dataset.prepare("train")
    print(f"训练集: {train_data.shape}")
    print(f"特征列 (前 10): {train_data.columns[:10].tolist()}")

    # 启动实验记录 (MLflow)
    with R.start(experiment_name="my_strategy"):
        print("训练模型中...")
        model.fit(dataset)

        # 记录信号（模型预测结果）
        recorder = R.get_recorder()
        sr = SignalRecord(model, dataset, recorder)
        sr.generate()

        # 信号分析 (IC / ICIR)
        sar = SigAnaRecord(recorder)
        sar.generate()

        # 回测 (年化收益 / 最大回撤 / 夏普)
        par = PortAnaRecord(recorder, port_analysis_config)
        par.generate()

    print("\n✓ 策略运行完成! 实验记录保存在 ./mlruns/ 目录")
