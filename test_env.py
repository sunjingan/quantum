"""测试 Qlib 环境的脚本，第一次使用时运行验证"""
import multiprocessing
import sys
sys.path.insert(0, '/Users/jingansun/Desktop/codex/quant/qlib')

import qlib
from qlib.utils import init_instance_by_config
from qlib.contrib.evaluate import backtest_daily

qlib.init(provider_uri='/Users/jingansun/Desktop/codex/quant/data/qlib', region='cn')

dh_conf = {
    "start_time": "2018-01-01", "end_time": "2020-08-01",
    "fit_start_time": "2018-01-01", "fit_end_time": "2019-12-31",
    "instruments": "csi300"
}

dataset = init_instance_by_config({
    "class": "DatasetH", "module_path": "qlib.data.dataset",
    "kwargs": {
        "handler": {"class": "Alpha158", "module_path": "qlib.contrib.data.handler", "kwargs": dh_conf},
        "segments": {"train": ("2018-01-01", "2019-12-31"), "test": ("2020-01-01", "2020-08-01")}
    }
})

X, y = dataset.prepare("train", col_set=["feature", "label"])
print(f"训练数据: {X.shape[0]} 样本 x {X.shape[1]} 特征")

model = init_instance_by_config({
    "class": "LGBModel", "module_path": "qlib.contrib.model.gbdt",
    "kwargs": {"loss": "mse", "num_threads": 1, "verbose": -1}
})
model.fit(dataset)

pred = model.predict(dataset, segment="test")
report, _ = backtest_daily(pred, strategy="topk50", topk=50, deal_price="close")

print("\n=== 回测结果 ===")
print(report.head(8).to_string())
print(f"\n✓ Qlib 环境验证通过!")

