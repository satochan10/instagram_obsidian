#!/bin/bash
# 毎朝10時に launchd から呼ばれる: 全投稿の数字を取得してdata/daily_log.csvに追記する
cd "$(dirname "$0")/.."
mkdir -p logs
./venv/bin/python scripts/fetch_data.py >> logs/daily_fetch.log 2>&1
