"""
画像投稿を公開する(フィード・単一画像のみ)。

事前にキャプションの承認が済んでいる前提で、コンテナ作成 → 即公開まで一括で行う。
確認ステップはこのスクリプトの外(Claudeとの会話)で完了している想定。

実行例:
  ./venv/bin/python scripts/publish_post.py \
    --image-url "https://www.dropbox.com/scl/fi/xxxx/photo.jpg?rlkey=yyy&dl=0" \
    --caption "承認済みのキャプション本文"
"""
import argparse
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
GRAPH_URL = "https://graph.instagram.com/v21.0"


def to_direct_dropbox_url(url: str) -> str:
    """Dropboxの共有リンクを直接ダウンロード可能なURLに変換する。"""
    if "dropbox.com" not in url:
        return url
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["dl"] = ["1"]
    new_query = urlencode({k: v[0] for k, v in query.items()})
    return urlunparse(parsed._replace(query=new_query))


def load_env():
    env = dotenv_values(ENV_PATH)
    token = env.get("IG_ACCESS_TOKEN", "").strip()
    ig_user_id = env.get("IG_USER_ID", "").strip()
    if not token or not ig_user_id:
        sys.exit(".envのIG_ACCESS_TOKEN / IG_USER_IDが未設定です。")
    return token, ig_user_id


def create_container(token, ig_user_id, image_url, caption):
    resp = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
    )
    if resp.status_code != 200:
        sys.exit(f"コンテナ作成に失敗しました: {resp.text}")
    return resp.json()["id"]


def wait_until_ready(token, container_id, timeout_sec=60):
    """コンテナの処理状況(FINISHED)を待つ。"""
    start = time.time()
    while time.time() - start < timeout_sec:
        resp = requests.get(
            f"{GRAPH_URL}/{container_id}",
            params={"fields": "status_code", "access_token": token},
        )
        if resp.status_code == 200:
            status = resp.json().get("status_code")
            if status == "FINISHED":
                return
            if status == "ERROR":
                sys.exit(f"コンテナ処理が失敗しました: {resp.json()}")
        time.sleep(2)
    sys.exit("コンテナの処理待ちがタイムアウトしました。")


def publish(token, ig_user_id, container_id):
    resp = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
    )
    if resp.status_code != 200:
        sys.exit(f"公開に失敗しました: {resp.text}")
    return resp.json()["id"]


def get_permalink(token, media_id):
    resp = requests.get(
        f"{GRAPH_URL}/{media_id}",
        params={"fields": "permalink", "access_token": token},
    )
    if resp.status_code == 200:
        return resp.json().get("permalink")
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-url", required=True, help="Dropbox等の画像共有リンク")
    parser.add_argument("--caption", required=True, help="承認済みのキャプション本文")
    args = parser.parse_args()

    token, ig_user_id = load_env()
    direct_url = to_direct_dropbox_url(args.image_url)

    print("コンテナを作成中...")
    container_id = create_container(token, ig_user_id, direct_url, args.caption)

    print("処理完了を待機中...")
    wait_until_ready(token, container_id)

    print("公開中...")
    media_id = publish(token, ig_user_id, container_id)

    permalink = get_permalink(token, media_id)
    print(f"公開しました: {permalink or media_id}")


if __name__ == "__main__":
    main()
