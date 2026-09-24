# Obsidian Properties UI — 設計スペック

## 背景・目的
Obsidian Vault（`/Users/satoru/dev/00_試行錯誤/00_Obsidian/脳`）の各ノートに `type` / `category` / `status` / `tags` のPropertiesを付与済み。これをコマンドやObsidian標準機能（Bases）を使わず、ブラウザで開くシンプルなHTML UIから検索・一覧できるようにする。

将来的にInstagram連携システム（`04_インスタ連携/`、現状CLI/チャット駆動）にもUIを追加し、1つのダッシュボードとして合体させる計画があるため、最初から共通の`web/`フォルダ・共通サーバー構成にしておく。

## スコープ（MVP）
- Vault内 `.md` ファイルのProperties（`type`/`category`/`status`/`tags`）による検索・一覧表示のみ
- 対象外（次フェーズ）：status更新、新規ノート作成、スキーマ一貫性チェック、Instagram側API統合

## ディレクトリ構造
```
04_インスタ連携/
├── web/
│   ├── server.py         # HTTPサーバ本体。/api/obsidian/* を提供（将来 /api/instagram/* を追加）
│   ├── index.html         # ダッシュボード入口（現時点ではobsidian.htmlへのリンクのみ）
│   └── obsidian.html      # Obsidianプロパティ検索・一覧UI（今回のMVP本体）
└── .env                    # OBSIDIAN_VAULT_PATH を追記
```

## バックエンド（web/server.py）
- Python標準ライブラリ `http.server` のみで実装（既存プロジェクトのCLIスクリプト群と同様、軽量フレームワーク不使用）
- 依存追加：`pyyaml`（フロントマター解析用。`venv/bin/pip install pyyaml`）
- ルーティング
  - `GET /` → `index.html` を配信
  - `GET /obsidian.html` → `obsidian.html` を配信
  - `GET /api/obsidian/notes?type=&category=&status=&tag=` → 条件に一致するノートをJSON配列で返す
    - 各要素：`{ path, title, type, category, status, tags, preview }`
    - `path` はVaultルートからの相対パス
    - `preview` は本文冒頭〜100文字程度（フロントマター除去後）
  - `GET /api/obsidian/facets` → 現在Vaultに実在する `type`/`category`/`status`/`tags` の値一覧（UIのプルダウン生成用）
- Vaultスキャン
  - `.env` の `OBSIDIAN_VAULT_PATH` を読み込み、配下の `*.md` を再帰的に走査（`.obsidian/` 配下は除外）
  - フロントマター（`---`で囲まれたYAMLブロック）をパース。無い/壊れている場合は `type: null` 等として扱い、結果からは除外せず「Properties未設定」として返す
- 起動
  - ポート8765固定
  - 起動時に `webbrowser.open("http://localhost:8765")` でブラウザを自動起動
  - `OBSIDIAN_VAULT_PATH` が未設定 or 実在しない場合はエラーメッセージを表示して起動を中止

## フロントエンド（web/obsidian.html）
- 素のHTML/CSS/JS（フレームワーク不使用、ビルド不要）
- 初期表示時に `/api/obsidian/facets` を呼び、type/category/statusのプルダウンを動的生成
- tagsはテキスト入力でAND検索（カンマ区切りで複数指定可）
- 検索結果はテーブル表示：タイトル／type／category／status／tags
- 行クリックで `preview` をその場に展開表示
- 各行に「Obsidianで開く」リンク（Obsidian公式URIスキーム `obsidian://open?vault=<Vault名>&file=<拡張子なし相対パス>` を使用。Vault名・パスは両方URLエンコードする）

## エラーハンドリング
- Properties未設定ノートは除外せず、テーブル末尾に別枠（「Properties未設定」グループ）で表示する
- Vaultパス不備時はサーバ起動を中止し、標準出力にエラーメッセージを表示する
- APIリクエストでVaultスキャンに失敗した場合は500エラーとエラーメッセージをJSONで返す

## テスト方針
- 自動テストは作成しない（個人利用のローカルツールのため）
- 実装後、実際の27ファイルのVaultに対してサーバを起動し、以下を目視確認する
  - facetsのプルダウンに実際の値（instagram/video/sns/obsidian/learning等）が出ること
  - type/category/status/tagsそれぞれの単独フィルタ、および組み合わせフィルタが正しく絞り込めること
  - Properties未設定のノート（TODO.md、USJ 朝並ぶ.md）が別枠に表示されること
  - 「Obsidianで開く」リンクでアプリが起動すること

## 今後の拡張（このスペックの対象外）
- statusのワンクリック更新
- フォームからの新規ノート作成（Properties自動付与）
- type/category表記ゆれの一貫性チェック
- `/api/instagram/*` の追加とダッシュボード統合
