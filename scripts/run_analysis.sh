#!/bin/bash
# 「分析して」で実行するワンコマンド: データ取得 + レポート生成
set -e
cd "$(dirname "$0")/.."
./venv/bin/python scripts/fetch_data.py
./venv/bin/python scripts/analyze.py
