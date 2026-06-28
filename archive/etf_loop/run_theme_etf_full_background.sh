#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT" || exit 1

timestamp() {
  date "+%Y-%m-%d %H:%M:%S"
}

trap 'rc=$?; echo "[$(timestamp)] wrapper: exit rc=$rc"' EXIT

echo "[$(timestamp)] wrapper: start"
echo "[$(timestamp)] wrapper: pwd=$PWD"

VENV_DIR="$PROJECT_ROOT/env_qlib"
if [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "[$(timestamp)] wrapper: missing venv $VENV_DIR"
  exit 1
fi

source "$VENV_DIR/bin/activate"
export QLIB_PROVIDER_URI=data/a_share_qlib
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/libomp/lib:${DYLD_LIBRARY_PATH:-}"
export PYTHONPATH="$PROJECT_ROOT/qlib:${PYTHONPATH:-}"
export MLFLOW_ALLOW_FILE_STORE=true
export QLIB_LAZY_TUSHARE=0
export PYTHONUNBUFFERED=1

echo "[$(timestamp)] wrapper: python=$(which python3)"
echo "[$(timestamp)] wrapper: qlib_provider=$QLIB_PROVIDER_URI"

echo "[$(timestamp)] wrapper: python probe begin"
python3 -u -c "print('python probe ok')"
rc=$?
echo "[$(timestamp)] wrapper: python probe rc=$rc"
if [ $rc -ne 0 ]; then
  exit $rc
fi


echo "[$(timestamp)] wrapper: prefetch begin"
python3 -u tools/data_prep/prefetch_theme_etf_data.py --start 2018-01-02 --end 2026-06-22 --market all_a
rc=$?
echo "[$(timestamp)] wrapper: prefetch rc=$rc"
if [ $rc -ne 0 ]; then
  exit $rc
fi

echo "[$(timestamp)] wrapper: runner begin"
python3 -u archive/etf_loop/run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22
rc=$?
echo "[$(timestamp)] wrapper: runner rc=$rc"
exit $rc
