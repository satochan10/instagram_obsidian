"""
トークンの検証・長期化・InstagramビジネスアカウントID自動取得。

実行: ./venv/bin/python scripts/check_token.py

やること:
1. .envのIG_ACCESS_TOKENが短期なら、FB_APP_ID/FB_APP_SECRETを使って60日間有効な長期トークンに交換
2. 長期トークンで連携中のFacebookページ一覧を取得し、紐づくInstagramアカウントIDを特定
3. .envのIG_ACCESS_TOKEN / IG_USER_ID / FB_PAGE_ID を更新
トークンの値そのものは標準出力に出さない(先頭6文字のみ表示)。
"""
import os
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values, set_key

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
GRAPH_URL = "https://graph.facebook.com/v21.0"


def mask(token: str) -> str:
    return token[:6] + "..." if token else "(空)"


def main():
    env = dotenv_values(ENV_PATH)
    token = env.get("IG_ACCESS_TOKEN", "").strip()
    app_id = env.get("FB_APP_ID", "").strip()
    app_secret = env.get("FB_APP_SECRET", "").strip()

    if not token:
        sys.exit(".envのIG_ACCESS_TOKENが空です。先に埋めてください。")

    # 1. 現状のトークンが有効か確認
    resp = requests.get(f"{GRAPH_URL}/me", params={"access_token": token})
    if resp.status_code != 200:
        sys.exit(f"トークンが無効です: {resp.status_code} {resp.text}")
    print(f"現在のトークン({mask(token)})は有効です。")

    # 2. 長期トークンに交換(app_id/secretがある場合)
    if app_id and app_secret:
        resp = requests.get(
            f"{GRAPH_URL}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": token,
            },
        )
        if resp.status_code == 200:
            long_token = resp.json()["access_token"]
            expires_in = resp.json().get("expires_in", "不明")
            token = long_token
            set_key(str(ENV_PATH), "IG_ACCESS_TOKEN", token)
            print(f"長期トークンに交換しました({mask(token)})。有効期限: 約{expires_in}秒後")
        else:
            print(f"長期トークンへの交換に失敗しました(短期のまま使用します): {resp.text}")
    else:
        print("FB_APP_ID/FB_APP_SECRETが未設定のため、長期トークン交換をスキップします。")

    # 3. Facebookページ経由でInstagramビジネスアカウントIDを特定
    resp = requests.get(
        f"{GRAPH_URL}/me/accounts",
        params={"access_token": token, "fields": "id,name,instagram_business_account"},
    )
    if resp.status_code != 200:
        sys.exit(f"Facebookページ一覧の取得に失敗しました: {resp.text}")

    pages = resp.json().get("data", [])
    ig_pages = [p for p in pages if p.get("instagram_business_account")]

    if not ig_pages:
        sys.exit(
            "Instagramアカウントが紐づいたFacebookページが見つかりません。"
            "Meta for Developersのアプリ設定でページ連携・Instagram連携を確認してください。"
        )

    if len(ig_pages) > 1:
        print("複数のページが見つかりました:")
        for p in ig_pages:
            print(f"  - {p['name']} (page_id={p['id']}, ig_id={p['instagram_business_account']['id']})")
        page = ig_pages[0]
        print(f"先頭の「{page['name']}」を使用します。別のものを使う場合は.envのFB_PAGE_ID/IG_USER_IDを手動で書き換えてください。")
    else:
        page = ig_pages[0]

    fb_page_id = page["id"]
    ig_user_id = page["instagram_business_account"]["id"]

    set_key(str(ENV_PATH), "FB_PAGE_ID", fb_page_id)
    set_key(str(ENV_PATH), "IG_USER_ID", ig_user_id)

    print(f"連携アカウント: {page['name']}")
    print(f"FB_PAGE_ID={fb_page_id}")
    print(f"IG_USER_ID={ig_user_id}")
    print(".envを更新しました。")


if __name__ == "__main__":
    main()
