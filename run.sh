#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "何をしますか？"
echo "1) 分析（投稿データ取得 → レポート作成）"
echo "2) 投稿（画像投稿を公開）"
echo "3) Obsidian UI（Vault内ノートのProperties検索）"
read -p "番号を選んでください: " choice

case "$choice" in
  1)
    ./scripts/run_analysis.sh
    ;;
  2)
    read -p "画像URL（Dropbox共有リンク）: " image_url
    read -p "キャプション: " caption
    ./venv/bin/python scripts/publish_post.py --image-url "$image_url" --caption "$caption"
    ;;
  3)
    ./venv/bin/python web/server.py
    ;;
  *)
    echo "1〜3のいずれかを選んでください"
    exit 1
    ;;
esac
