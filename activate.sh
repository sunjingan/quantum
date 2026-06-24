#!/bin/bash
# ==========================================
# Qlib 环境激活脚本（conda 风格）
# 使用: source activate.sh
# 之后直接 python your_script.py 即可
# ==========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/env_qlib"

# 检查 venv 是否存在
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "错误: 虚拟环境 $VENV_DIR 不存在"
    echo "请先运行: python3 -m venv env_qlib && env_qlib/bin/pip install -e qlib/."
    return 1 2>/dev/null || exit 1
fi

# 激活 Python 虚拟环境
source "$VENV_DIR/bin/activate"

# 设置环境变量
export QLIB_PROVIDER_URI="$SCRIPT_DIR/data/my_qlib"
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/libomp/lib:$DYLD_LIBRARY_PATH"

# Python 路径（确保能找到 qlib 包）
export PYTHONPATH="$SCRIPT_DIR/qlib:$PYTHONPATH"

echo "Qlib 环境已激活"
echo "  Python:   $(which python3)"
echo "  Qlib数据: $QLIB_PROVIDER_URI"
echo "  LightGBM: $(python3 -c 'import lightgbm; print(lightgbm.__version__)' 2>/dev/null || echo '未安装')"

export MLFLOW_ALLOW_FILE_STORE=true
