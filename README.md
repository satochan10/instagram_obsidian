# Instagram連携・分析プロジェクト

Instagram Graph API（Instagram単体ログイン方式）に接続し、投稿データ・インサイトを取得してアカウント分析レポートを作るための一式。

## クイックスタート

### Claudeに指示する場合
チャットで一言「**分析して**」と言うだけでよい。裏で `run_analysis.sh` が実行され、レポートが生成・表示される。

投稿を公開したい場合は、Dropboxの共有リンクとキャプション案を渡して会話する。Claudeが下書きを提示し、「OK」と返すと `publish_post.py` が実行されて公開される。

### 自分でコマンドを打つ場合
```bash
# 分析レポートを生成(投稿データ取得 → レポート作成)
./scripts/run_analysis.sh

# 画像投稿を公開(キャプションは事前に承認済みのものを渡す)
./venv/bin/python scripts/publish_post.py \
  --image-url "https://www.dropbox.com/scl/fi/xxxx/photo.jpg?rlkey=yyy&dl=0" \
  --caption "承認済みのキャプション本文"

# 毎朝10時の自動実行を止める/再開する
launchctl unload ~/Library/LaunchAgents/com.tomo.ig-daily-fetch.plist
launchctl load ~/Library/LaunchAgents/com.tomo.ig-daily-fetch.plist
```

## できること

- **「分析して」の一言で** 全投稿のキャプション・数字（リーチ/いいね/コメント/保存/シェア/再生数/平均視聴時間）とフォロワー数を取得し、Markdownレポートを自動生成
- レポート内で「伸びた投稿TOP3」を自動抽出（投稿から48時間以上経過した投稿のみを対象にし、取得できない値は推測せず「データ不足」と明記）
- **毎朝10時に自動実行**され、その日時点の全投稿の数字を`data/daily_log.csv`に追記（時系列で蓄積）
- トークンの検証・長期化・アカウントID自動取得（`check_token.py`、現行のIG単体ログイン方式では未使用）

- **画像投稿の自動公開**（`scripts/publish_post.py`）。Dropboxの共有リンクと承認済みキャプションを渡すと、Instagramのフィードに画像を公開する。キャプションの下書き生成・確認はClaudeとの会話内で行い、「OK」が出たものだけを公開する運用（スクリプト自体には確認ステップはない）

- **ローカルUI（`./venv/bin/python web/server.py`を起動）から** Obsidian VaultノートのProperties（type/category/status/tags）を検索・一覧表示（`web/obsidian.html`）

現時点でできないこと（詳細は「今後の課題」参照）：トークンの自動更新、他アカウントの人気投稿分析、コメント自動返信、カルーセル/リール投稿、投稿のスケジュール予約。

## 連携方式について

このアカウント（クリエイターアカウント、Facebookページ未連携）は **Instagram API with Instagram Login**（2024年以降の新方式）で連携している。そのため：

- APIのベースURLは `https://graph.facebook.com` ではなく **`https://graph.instagram.com`**
- アクセストークンは `IGAA...` から始まる形式（Facebook側の `EAAxxx` トークンとは別物で、`graph.facebook.com` 側では使えない）
- **ハッシュタグ検索API（`ig_hashtag_search`）は使えない**（Facebookページ連携の旧方式でのみ利用可能なため、他アカウントの人気投稿分析はこの構成では不可）
- トークンはInstagramアプリ側の管理画面（Meta for Developers → 該当アプリ → ユースケース → Instagramでメッセージとコンテンツを管理 → API設定 → ユーザートークンジェネレーター）から発行する

## ディレクトリ構成

```
.
├── .env                  # 認証情報(gitignore対象・絶対に共有しない)
├── .env.example          # .envのひな形
├── venv/                 # Python仮想環境
├── scripts/
│   ├── publish_post.py    # 画像投稿を公開(コンテナ作成→即公開)。承認済みキャプション前提
│   ├── check_token.py    # トークン検証・長期化・Facebookページ経由のID自動取得(旧方式向け。今回のIG単体ログインでは未使用)
│   ├── fetch_data.py     # 投稿一覧・インサイト・フォロワー情報を取得するメイン処理
│   ├── analyze.py        # data/latest.json からMarkdownレポートを生成
│   ├── run_analysis.sh   # fetch_data.py → analyze.py を一括実行(「分析して」で呼ぶコマンド)
│   └── daily_fetch.sh    # 毎朝10時の自動実行から呼ばれるラッパー(fetch_data.pyのみ実行)
├── data/
│   ├── latest.json       # 直近の取得結果(全データ)
│   ├── snapshot_*.json   # 実行ごとのタイムスタンプ付きスナップショット
│   └── daily_log.csv     # 毎朝の自動実行で1行ずつ追記される時系列ログ
├── reports/
│   └── report_*.md       # analyze.pyが生成する日付付きレポート
├── logs/
│   ├── daily_fetch.log       # daily_fetch.sh実行時の標準出力
│   ├── launchd.out.log       # launchdからの標準出力
│   └── launchd.err.log       # launchdからの標準エラー
└── web/
    ├── server.py          # ローカルダッシュボード用HTTPサーバ(Obsidian Properties検索など)。 /api/obsidian/* を提供
    └── obsidian.html       # Obsidian VaultのProperties検索UI
```

## セットアップ済みの内容

### 1. 認証情報 (`.env`)
| 変数 | 内容 |
|---|---|
| `IG_ACCESS_TOKEN` | Instagramユーザートークン(`IGAA...`)。長期(60日)想定だが期限管理は未実装(下記「今後の課題」参照) |
| `IG_USER_ID` | Instagram User ID (`17841426619222104`) |
| `FB_APP_ID` / `FB_APP_SECRET` / `FB_PAGE_ID` | 旧Facebookページ連携方式用に残しているが、現行構成では未使用 |

### 2. データ取得 (`scripts/fetch_data.py`)
- 直近90日分の投稿を取得。**90日以内の投稿が30本未満の場合は全期間を対象にする**
- ストーリーズは取得対象から除外(24時間で消えるため)
- 投稿ごとに `hours_since_posted` を計算し、48時間未満かどうかを保持(「伸びなかった」判定からの除外に使う)
- フィードは `reach, likes, comments, saved, shares, total_interactions`、リールは追加で `views, ig_reels_avg_watch_time, ig_reels_video_view_total_time` を取得
- フォロワーの年齢層・性別は `follower_demographics` インサイトから取得を試みるが、**フォロワー数が一定数に満たないと空になる**(Instagram側の仕様。推測で埋めず「データ不足」と表示する)
- 取得結果は `data/latest.json`（最新）と `data/snapshot_日時.json`（履歴）に保存
- 実行のたびに `data/daily_log.csv` に1行ずつ追記(毎朝の自動実行はこのログを溜めるのが目的)

### 3. レポート生成 (`scripts/analyze.py`)
- `data/latest.json` を読み込み、`reports/report_日付.md` を生成
- 投稿一覧テーブル、伸びた投稿TOP3（**投稿から48時間以上経過し、エンゲージ率が算出できた投稿のみが対象**）、全体平均をまとめる
- 取得できなかった値は推測せず、すべて「データ不足」と明記する

### 4. 毎朝10時の自動実行
- `~/Library/LaunchAgents/com.tomo.ig-daily-fetch.plist` にlaunchdジョブを登録済み（`launchctl load`実行済み）
- 毎朝10時に `scripts/daily_fetch.sh` → `scripts/fetch_data.py` が実行され、`data/daily_log.csv` に追記される
- **Macがスリープ/シャットダウン中は実行されない**（launchdの制約。次に起動したタイミングでは自動的に走らない点に注意。必要なら`RunAtLoad`や`StartInterval`の追加を検討）

## 使い方

### 「分析して」と言われたら
```bash
./scripts/run_analysis.sh
```
を実行する（fetch_data.py → analyze.py を順番に実行し、レポートを表示・保存する）。

### 自動実行を止めたい場合
```bash
launchctl unload ~/Library/LaunchAgents/com.tomo.ig-daily-fetch.plist
```

### 自動実行を再開したい場合
```bash
launchctl load ~/Library/LaunchAgents/com.tomo.ig-daily-fetch.plist
```

## 今後の課題

- **トークンの有効期限管理が未実装。** 現状のトークンは発行時点でおそらく60日程度有効だが、自動更新（`refresh_access_token`）の仕組みは組んでいない。期限切れ間近になったら手動でユーザートークンジェネレーターから再発行が必要。60日ごとにリマインドするか、自動リフレッシュ処理を追加するのが望ましい。
- **投稿数が少ない（現状6本）ため、「伸びた投稿TOP3」分析は参考程度。** データが溜まってから本格的な傾向分析に使う想定。
- **他アカウントの人気投稿分析（ハッシュタグ検索）は現行の連携方式では不可。** 必要になった場合はFacebookページ連携への切り替えが必要（トークン体系が変わるため要再設計）。
- コメント自動返信の仕組みは未着手。
