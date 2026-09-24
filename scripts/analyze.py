"""
data/latest.json を元にアカウント分析レポート(Markdown)を作成する。

実行: ./venv/bin/python scripts/analyze.py

前提:
- 投稿から48時間経っていない投稿は「伸びなかった投稿」判定から除外する
  (表には出すが、TOP/WORST判定の対象外であることを明記)
- 取得できなかった項目は推測せず「データ不足」と明記する
- ストーリーズはfetch_data.py側で除外済み
"""
import json
from datetime import datetime
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "latest.json"
REPORT_DIR = ROOT / "reports"

NA = "データ不足"


def fmt(v):
    return NA if v is None else v


def engagement_rate(insights):
    reach = insights.get("reach")
    interactions = insights.get("total_interactions")
    if reach is None or interactions is None or reach == 0:
        return None
    return round(interactions / reach * 100, 2)


def caption_excerpt(caption, n=40):
    if not caption:
        return "(キャプションなし)"
    caption = caption.replace("\n", " ")
    return caption[:n] + ("…" if len(caption) > n else "")


def build_report(data):
    account = data.get("account", {})
    demographics = data.get("follower_demographics", {})
    media = data.get("media", [])
    fetched_at = data.get("fetched_at")
    period_note = data.get("period_note")

    lines = []
    lines.append(f"# Instagramアカウント分析レポート")
    lines.append(f"")
    lines.append(f"- 対象アカウント: @{account.get('username', NA)}")
    lines.append(f"- アカウント種別: {account.get('account_type', NA)}")
    lines.append(f"- 分析期間: {period_note}")
    lines.append(f"- データ取得日時: {fetched_at}")
    lines.append(f"")

    # フォロワー数・年齢層
    lines.append("## フォロワー")
    lines.append(f"- フォロワー数: {fmt(account.get('followers_count'))}")
    for label, key in [("年齢層", "age"), ("性別", "gender")]:
        entries = demographics.get(key, {}).get("data", [])
        if entries and entries[0].get("total_value", {}).get("breakdowns"):
            lines.append(f"- {label}: (データあり。生データはdata/latest.jsonを参照)")
        else:
            lines.append(
                f"- {label}: {NA}"
                "(Instagram側の仕様でフォロワー数が一定数に満たない場合は取得不可のことがあります)"
            )
    lines.append("")

    # 投稿一覧テーブル
    lines.append("## 全投稿サマリー")
    lines.append("")
    lines.append("| 投稿日時 | 種別 | 経過時間 | リーチ | いいね | コメント | 保存 | シェア | 再生数 | 平均視聴時間(秒) | エンゲージ率 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")

    rows = []
    for m in media:
        ins = m.get("insights", {})
        posted_at = m["timestamp"]
        hours = m["hours_since_posted"]
        eligible = hours >= 48
        avg_watch = ins.get("ig_reels_avg_watch_time")
        avg_watch_sec = round(avg_watch / 1000, 1) if isinstance(avg_watch, (int, float)) else NA
        row = {
            "id": m["id"],
            "posted_at": posted_at,
            "type": m.get("media_product_type"),
            "hours": hours,
            "eligible": eligible,
            "caption": caption_excerpt(m.get("caption")),
            "reach": ins.get("reach"),
            "likes": ins.get("likes"),
            "comments": ins.get("comments"),
            "saved": ins.get("saved"),
            "shares": ins.get("shares"),
            "views": ins.get("views"),
            "avg_watch_sec": avg_watch_sec,
            "engagement_rate": engagement_rate(ins),
        }
        rows.append(row)
        lines.append(
            f"| {posted_at[:10]} | {row['type']} | {hours:.0f}h"
            f"{'' if eligible else '(48h未満)'} | {fmt(row['reach'])} | {fmt(row['likes'])} | "
            f"{fmt(row['comments'])} | {fmt(row['saved'])} | {fmt(row['shares'])} | "
            f"{fmt(row['views'])} | {fmt(row['avg_watch_sec'])} | "
            f"{fmt(row['engagement_rate'])}{'%' if row['engagement_rate'] is not None else ''} |"
        )
    lines.append("")

    # TOP3 / WORST(48h経過済みのみ対象)
    eligible_rows = [r for r in rows if r["eligible"] and r["engagement_rate"] is not None]
    excluded_count = len(rows) - len(eligible_rows)

    lines.append("## 伸びた投稿 TOP3(エンゲージ率基準、投稿から48時間以上経過した投稿のみ対象)")
    lines.append("")
    if excluded_count:
        lines.append(f"※ 投稿から48時間未満、またはエンゲージ率算出不可のため{excluded_count}件を判定対象外としています。")
        lines.append("")
    if not eligible_rows:
        lines.append(f"判定対象の投稿がありません({NA})。")
    else:
        top3 = sorted(eligible_rows, key=lambda r: r["engagement_rate"], reverse=True)[:3]
        for i, r in enumerate(top3, 1):
            lines.append(
                f"{i}. {r['posted_at'][:10]} ({r['type']}) エンゲージ率{r['engagement_rate']}% "
                f"/ リーチ{fmt(r['reach'])} / キャプション: {r['caption']}"
            )
    lines.append("")

    # 平均値
    def avg_of(key):
        vals = [r[key] for r in rows if isinstance(r[key], (int, float))]
        return round(mean(vals), 2) if vals else None

    lines.append("## 全体平均(取得できた投稿のみ)")
    lines.append(f"- 平均リーチ: {fmt(avg_of('reach'))}")
    lines.append(f"- 平均いいね: {fmt(avg_of('likes'))}")
    lines.append(f"- 平均コメント: {fmt(avg_of('comments'))}")
    lines.append(f"- 平均保存: {fmt(avg_of('saved'))}")
    lines.append(f"- 平均シェア: {fmt(avg_of('shares'))}")
    lines.append(f"- 平均エンゲージ率: {fmt(avg_of('engagement_rate'))}{'%' if avg_of('engagement_rate') is not None else ''}")
    lines.append("")

    return "\n".join(lines)


def main():
    if not DATA_PATH.exists():
        raise SystemExit("data/latest.jsonがありません。先に fetch_data.py を実行してください。")
    data = json.loads(DATA_PATH.read_text())
    report = build_report(data)

    REPORT_DIR.mkdir(exist_ok=True)
    out_path = REPORT_DIR / f"report_{datetime.now().strftime('%Y-%m-%d')}.md"
    out_path.write_text(report)
    print(report)
    print(f"\n---\n保存しました: {out_path}")


if __name__ == "__main__":
    main()
