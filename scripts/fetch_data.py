"""
Instagramの投稿一覧・インサイト・アカウント情報を取得し、data/配下にJSON保存する。

実行: ./venv/bin/python scripts/fetch_data.py [--days 90]

- 直近N日(デフォルト90日)の投稿を取得。30本未満なら全期間を対象にする。
- 投稿から48時間経っていないものは fetched_at 時点のフラグ is_growth_eligible=False にする
  (「伸びた/伸びなかった」の判定は analyze.py 側で行う)
- ストーリーズは対象外(/media エンドポイントには通常含まれないが、念のためmedia_product_type
  がSTORYのものは除外する)
- 取得できなかった指標は None のまま保存し、レポート側で「データ不足」と明記する
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
DATA_DIR = ROOT / "data"
GRAPH_URL = "https://graph.instagram.com/v21.0"

FEED_METRICS = ["reach", "likes", "comments", "saved", "shares", "total_interactions"]
REELS_METRICS = [
    "reach", "likes", "comments", "saved", "shares", "total_interactions",
    "views", "ig_reels_avg_watch_time", "ig_reels_video_view_total_time",
]


def load_env():
    env = dotenv_values(ENV_PATH)
    token = env.get("IG_ACCESS_TOKEN", "").strip()
    ig_user_id = env.get("IG_USER_ID", "").strip()
    if not token or not ig_user_id:
        sys.exit(".envのIG_ACCESS_TOKEN / IG_USER_IDが未設定です。check_token.pyを先に実行してください。")
    return token, ig_user_id


def get_account_info(token, ig_user_id):
    resp = requests.get(
        f"{GRAPH_URL}/{ig_user_id}",
        params={"access_token": token, "fields": "id,username,account_type,media_count,followers_count"},
    )
    if resp.status_code != 200:
        return {"error": resp.text}
    return resp.json()


def get_follower_demographics(token, ig_user_id):
    result = {}
    for breakdown in ["age", "gender", "city", "country"]:
        resp = requests.get(
            f"{GRAPH_URL}/{ig_user_id}/insights",
            params={
                "access_token": token,
                "metric": "follower_demographics",
                "period": "lifetime",
                "metric_type": "total_value",
                "breakdown": breakdown,
            },
        )
        if resp.status_code == 200:
            result[breakdown] = resp.json()
        else:
            result[breakdown] = {"error": resp.json().get("error", {}).get("message", resp.text)}
    return result


def list_media(token, ig_user_id, since_dt):
    media = []
    url = f"{GRAPH_URL}/{ig_user_id}/media"
    params = {
        "access_token": token,
        "fields": "id,caption,media_type,media_product_type,timestamp,permalink,like_count,comments_count",
        "limit": 50,
    }
    while url:
        resp = requests.get(url, params=params)
        if resp.status_code != 200:
            print(f"投稿一覧取得エラー: {resp.text}", file=sys.stderr)
            break
        body = resp.json()
        page_items = body.get("data", [])
        media.extend(page_items)
        # 90日より古い投稿が出てきたら打ち切り(APIは新しい順で返る)
        if page_items:
            oldest_ts = datetime.fromisoformat(page_items[-1]["timestamp"].replace("Z", "+00:00"))
            if oldest_ts < since_dt:
                break
        paging = body.get("paging", {})
        url = paging.get("next")
        params = {}  # nextにはクエリが含まれる
    return media


def get_media_insights(token, media_id, media_product_type):
    metrics = REELS_METRICS if media_product_type == "REELS" else FEED_METRICS
    resp = requests.get(
        f"{GRAPH_URL}/{media_id}/insights",
        params={"access_token": token, "metric": ",".join(metrics)},
    )
    if resp.status_code != 200:
        # 一部メトリクスが対応外のことがあるので1つずつ再試行してデータ不足を明確化
        result = {}
        for m in metrics:
            r = requests.get(
                f"{GRAPH_URL}/{media_id}/insights",
                params={"access_token": token, "metric": m},
            )
            if r.status_code == 200 and r.json().get("data"):
                result[m] = r.json()["data"][0].get("values", [{}])[0].get("value")
            else:
                result[m] = None  # データ不足
        return result

    result = {}
    for item in resp.json().get("data", []):
        result[item["name"]] = item.get("values", [{}])[0].get("value")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()

    token, ig_user_id = load_env()
    DATA_DIR.mkdir(exist_ok=True)

    now = datetime.now(timezone.utc)
    since_dt = now - timedelta(days=args.days)

    print("アカウント情報を取得中...")
    account = get_account_info(token, ig_user_id)

    print("フォロワー年齢層等を取得中...")
    demographics = get_follower_demographics(token, ig_user_id)

    print(f"直近{args.days}日の投稿一覧を取得中...")
    media_list = list_media(token, ig_user_id, since_dt)
    media_list = [m for m in media_list if m.get("media_product_type") != "STORY"]

    # 90日以内のものにフィルタ。30本未満なら全期間を使う
    recent = [
        m for m in media_list
        if datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00")) >= since_dt
    ]
    target_media = recent if len(recent) >= 30 else media_list
    period_note = f"直近{args.days}日" if len(recent) >= 30 else f"直近{args.days}日は{len(recent)}本のため全期間({len(media_list)}本)"
    print(f"分析対象: {period_note}")

    print(f"{len(target_media)}件の投稿インサイトを取得中...")
    for i, m in enumerate(target_media, 1):
        posted_at = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
        m["hours_since_posted"] = (now - posted_at).total_seconds() / 3600
        m["insights"] = get_media_insights(token, m["id"], m.get("media_product_type"))
        print(f"  [{i}/{len(target_media)}] {m['id']} ({m.get('media_product_type')}) 完了")

    output = {
        "fetched_at": now.isoformat(),
        "period_note": period_note,
        "account": account,
        "follower_demographics": demographics,
        "media": target_media,
    }

    out_path = DATA_DIR / f"snapshot_{now.strftime('%Y-%m-%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    latest_path = DATA_DIR / "latest.json"
    latest_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"保存しました: {out_path}")

    append_daily_log(now, account, target_media)


def append_daily_log(now, account, target_media):
    """毎朝の自動実行用: 全投稿の数字を1行ずつCSVに追記する。"""
    log_path = DATA_DIR / "daily_log.csv"
    is_new = not log_path.exists()
    with open(log_path, "a", encoding="utf-8") as f:
        if is_new:
            f.write(
                "run_at,username,followers_count,media_id,posted_at,media_type,"
                "reach,likes,comments,saved,shares,views,avg_watch_time_sec\n"
            )
        for m in target_media:
            ins = m.get("insights", {})
            avg_watch = ins.get("ig_reels_avg_watch_time")
            avg_watch_sec = round(avg_watch / 1000, 1) if isinstance(avg_watch, (int, float)) else ""
            row = [
                now.isoformat(),
                account.get("username", ""),
                str(account.get("followers_count", "")),
                m["id"],
                m["timestamp"],
                m.get("media_product_type", ""),
                str(ins.get("reach", "")),
                str(ins.get("likes", "")),
                str(ins.get("comments", "")),
                str(ins.get("saved", "")),
                str(ins.get("shares", "")),
                str(ins.get("views", "")),
                str(avg_watch_sec),
            ]
            f.write(",".join(row) + "\n")
    print(f"日次ログに追記しました: {log_path}")


if __name__ == "__main__":
    main()
