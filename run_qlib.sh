#!/bin/bash
# Qlib environment wrapper
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/libomp/lib:$DYLD_LIBRARY_PATH"
VENV="/Users/jingansun/Desktop/codex/quant/qlib-venv"
cd /Users/jingansun/Desktop/codex/quant
"$VENV/bin/python3" "$@"
