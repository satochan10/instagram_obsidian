# Obsidian Properties UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ブラウザで開くローカルHTML UIから、Obsidian Vault内ノートのProperties（type/category/status/tags）を検索・一覧表示できるようにする。

**Architecture:** `04_インスタ連携/web/server.py`（Python標準ライブラリの`http.server`）がVault内`.md`をスキャンしてフロントマターをパースし、`/api/obsidian/*` エンドポイントでJSONを返す。`web/obsidian.html`（素のHTML/JS）がそれを叩いてテーブル表示する。将来Instagram側のUIも同じ`web/`配下・同じサーバーに追加する前提。

**Tech Stack:** Python 3（標準ライブラリ `http.server` / `pathlib` / `re` / `json` / `urllib.parse` / `webbrowser`）、`python-dotenv`（インストール済み）、`pyyaml`（今回追加）。フロントエンドはフレームワーク無しのHTML/CSS/JS。

**Spec:** `docs/superpowers/specs/2026-09-24-obsidian-properties-ui-design.md`

## Global Constraints

- サーバーはポート8765固定で起動し、起動時に `webbrowser.open()` でブラウザを自動オープンする（スペック記載）
- Vaultパスは `.env` の `OBSIDIAN_VAULT_PATH` から読み込む。未設定/存在しない場合はエラーメッセージを表示して起動を中止する（スペック記載）
- `.obsidian/` 配下は走査対象から除外する（スペック記載）
- フロントマターが無い/壊れているノートは除外せず「Properties未設定」として結果に含める（スペック記載）
- このプロジェクトはGit管理されていない（`git rev-parse --is-inside-work-tree` が失敗することを確認済み）。**各タスク末尾は「commit」ではなく「動作確認」を最終ステップとする**（通常のwriting-plansの型からの意図的な逸脱）
- 自動テスト（pytest等）は作成しない。スペック記載の通り、実際のVault（27ファイル）に対する目視・curl確認で代替する（意図的な逸脱）

---

### Task 1: 環境準備（依存追加・.env設定・ディレクトリ作成）

**Files:**
- Modify: `.env`（`OBSIDIAN_VAULT_PATH` を追記。既存の秘匿情報行はそのまま維持し、末尾に追記する）
- Modify: `.env.example`（同じキーをダミー値で追記）
- Create: `web/`（空ディレクトリ）

**Interfaces:**
- Produces: `.env` に `OBSIDIAN_VAULT_PATH` キーが存在する状態（Task 2以降の `dotenv_values()` 読み込みが依存）
- Produces: `venv` に `pyyaml` がインストールされた状態（Task 2の `import yaml` が依存）

- [ ] **Step 1: pyyamlをvenvにインストール**

Run: `./venv/bin/pip install pyyaml`
Expected: `Successfully installed pyyaml-...` が出力される

- [ ] **Step 2: インストール確認**

Run: `./venv/bin/python -c "import yaml; print(yaml.__version__)"`
Expected: バージョン番号が表示される（エラーなし）

- [ ] **Step 3: .envにOBSIDIAN_VAULT_PATHを追記**

既存の`.env`の中身は絶対に上書きしない。末尾に追記するだけにする。

Run:
```bash
printf '\n# Obsidian Properties UI用\nOBSIDIAN_VAULT_PATH="/Users/satoru/dev/00_試行錯誤/00_Obsidian/脳"\n' >> .env
```

- [ ] **Step 4: .env.exampleにも同じキーをダミー値で追記**

```bash
printf '\n# Obsidian Vaultのルートパス（obsidian_ui用）\nOBSIDIAN_VAULT_PATH=\n' >> .env.example
```

- [ ] **Step 5: webディレクトリを作成**

Run: `mkdir -p web`

- [ ] **Step 6: 動作確認**

Run: `grep OBSIDIAN_VAULT_PATH .env .env.example && ls -d web`
Expected: 両方の`.env`系ファイルに`OBSIDIAN_VAULT_PATH`の行があり、`web`ディレクトリが存在する

---

### Task 2: Vaultスキャン・フロントマター解析ロジック

**Files:**
- Create: `web/server.py`（このタスクでは以下の純粋関数部分のみ実装。HTTPハンドラはTask 3で追加する）

**Interfaces:**
- Consumes: `.env` の `OBSIDIAN_VAULT_PATH`（Task 1で追加済み）
- Produces:
  - `get_vault_path() -> Path` — Vaultルートの絶対パスを返す。未設定/不在なら `SystemExit` を送出
  - `parse_note(path: Path, vault_root: Path) -> dict` — 1ノートを `{path, title, type, category, status, tags, preview}` に変換
  - `scan_vault(vault_root: Path) -> list[dict]` — Vault内全`.md`を`parse_note`した結果のリスト
  - `filter_notes(notes: list[dict], query: dict) -> list[dict]` — `type`/`category`/`status`/`tag`（カンマ区切り文字列）で絞り込む
  - `build_facets(notes: list[dict]) -> dict` — `{"type": [...], "category": [...], "status": [...], "tags": [...]}`（Vault内に実在する値のソート済みユニーク一覧）
  - Task 3はこれら5関数と、この後追加する `VAULT_ROOT`（グローバル変数）を使う

- [ ] **Step 1: server.pyに純粋関数群を実装**

```python
"""
Obsidian Vault内ノートのPropertiesを検索・一覧表示するローカルUI用サーバー。

起動: ./venv/bin/python web/server.py
ブラウザで http://localhost:8765 が自動的に開く。
"""
import json
import re
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
WEB_DIR = Path(__file__).resolve().parent
PORT = 8765

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def get_vault_path() -> Path:
    env = dotenv_values(ENV_PATH)
    vault = env.get("OBSIDIAN_VAULT_PATH")
    if not vault:
        raise SystemExit("OBSIDIAN_VAULT_PATH が .env に設定されていません")
    path = Path(vault).expanduser()
    if not path.is_dir():
        raise SystemExit(f"OBSIDIAN_VAULT_PATH が存在しません: {path}")
    return path


def parse_note(path: Path, vault_root: Path) -> dict:
    import yaml

    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if match:
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            frontmatter = {}
        body = match.group(2)
    else:
        frontmatter = {}
        body = text

    title_match = TITLE_RE.search(body)
    title = title_match.group(1).strip() if title_match else path.stem

    preview = re.sub(r"\s+", " ", body).strip()[:100]

    tags = frontmatter.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]

    return {
        "path": path.relative_to(vault_root).as_posix(),
        "title": title,
        "type": frontmatter.get("type"),
        "category": frontmatter.get("category"),
        "status": frontmatter.get("status"),
        "tags": tags,
        "preview": preview,
    }


def scan_vault(vault_root: Path) -> list:
    notes = []
    for md_path in sorted(vault_root.rglob("*.md")):
        if ".obsidian" in md_path.parts:
            continue
        notes.append(parse_note(md_path, vault_root))
    return notes


def filter_notes(notes: list, query: dict) -> list:
    def matches(note):
        for key in ("type", "category", "status"):
            wanted = query.get(key)
            if wanted and note.get(key) != wanted:
                return False
        tag_param = query.get("tag")
        if tag_param:
            wanted_tags = [t.strip() for t in tag_param.split(",") if t.strip()]
            note_tags = note.get("tags") or []
            if not all(t in note_tags for t in wanted_tags):
                return False
        return True

    return [n for n in notes if matches(n)]


def build_facets(notes: list) -> dict:
    facets = {"type": set(), "category": set(), "status": set(), "tags": set()}
    for note in notes:
        for key in ("type", "category", "status"):
            if note.get(key):
                facets[key].add(note[key])
        for tag in note.get("tags") or []:
            facets["tags"].add(tag)
    return {key: sorted(values) for key, values in facets.items()}


if __name__ == "__main__":
    vault_root = get_vault_path()
    notes = scan_vault(vault_root)
    print(json.dumps(build_facets(notes), ensure_ascii=False, indent=2))
    print(f"{len(notes)} 件のノートをスキャンしました")
```

（`if __name__ == "__main__":` ブロックはこのタスクでは動作確認用の仮実装。Task 3でHTTPサーバー起動処理に置き換える）

- [ ] **Step 2: 実際のVaultに対して動作確認**

Run: `./venv/bin/python web/server.py`
Expected:
- `type`/`category`/`status`/`tags`のリストがJSONで表示される（例: `"type": ["checklist", "draft", "goal", "idea", ...]`）
- 末尾に `27 件のノートをスキャンしました` のように総数が表示される（`.obsidian`配下は含まれないため、`*.md`の実ファイル数と一致すること）

- [ ] **Step 3: filter_notesの動作確認**

Run:
```bash
./venv/bin/python -c "
from web.server import get_vault_path, scan_vault, filter_notes
notes = scan_vault(get_vault_path())
result = filter_notes(notes, {'category': 'instagram', 'status': 'active'})
for n in result:
    print(n['path'], n['type'], n['status'])
"
```
Expected: `category: instagram` かつ `status: active` のノートだけが表示される（0件でもエラーにならないこと）

- [ ] **Step 4: Properties未設定ノートが除外されずに含まれることを確認**

Run:
```bash
./venv/bin/python -c "
from web.server import get_vault_path, scan_vault
notes = scan_vault(get_vault_path())
no_props = [n for n in notes if not n['type'] and not n['category'] and not n['status']]
for n in no_props:
    print(n['path'], n['title'])
"
```
Expected: `TODO.md` と `USJ 朝並ぶ.md` の2件が表示される

---

### Task 3: HTTPサーバー・APIエンドポイント

**Files:**
- Modify: `web/server.py`（Task 2の関数群はそのまま、`if __name__ == "__main__":` ブロックをHTTPサーバー起動処理に置き換え、`Handler`クラスを追加）

**Interfaces:**
- Consumes: Task 2の `get_vault_path`, `scan_vault`, `filter_notes`, `build_facets`
- Produces:
  - `GET /` → `web/index.html` を返す（Task 5で作成。このタスク時点ではまだファイルが無いので404で構わない）
  - `GET /obsidian.html` → `web/obsidian.html` を返す（Task 4で作成。このタスク時点ではまだ無いので404で構わない）
  - `GET /api/obsidian/facets` → `{"type": [...], "category": [...], "status": [...], "tags": [...], "vault_name": "脳"}`
  - `GET /api/obsidian/notes?type=&category=&status=&tag=` → ノート配列のJSON
  - Vaultスキャン失敗時は500ステータス＋`{"error": "..."}`

- [ ] **Step 1: HTTPハンドラを実装（server.pyの末尾、`if __name__ == "__main__":`より上に追加）**

```python
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import webbrowser

VAULT_ROOT = None  # main()実行時にセットされる


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._serve_file(WEB_DIR / "index.html", "text/html")
            elif parsed.path == "/obsidian.html":
                self._serve_file(WEB_DIR / "obsidian.html", "text/html")
            elif parsed.path == "/api/obsidian/facets":
                notes = scan_vault(VAULT_ROOT)
                facets = build_facets(notes)
                facets["vault_name"] = VAULT_ROOT.name
                self._serve_json(facets)
            elif parsed.path == "/api/obsidian/notes":
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                notes = scan_vault(VAULT_ROOT)
                self._serve_json(filter_notes(notes, qs))
            else:
                self.send_error(404)
        except Exception as exc:  # noqa: BLE001 - Vaultスキャン失敗を500で返すため意図的に広く捕捉
            self._serve_json({"error": str(exc)}, status=500)

    def _serve_file(self, path: Path, content_type: str):
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_json(self, obj, status: int = 200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):  # noqa: A002 - BaseHTTPRequestHandlerのシグネチャに合わせる
        pass  # 標準出力へのアクセスログは出さない（個人ローカルツールのため）


def main():
    global VAULT_ROOT
    VAULT_ROOT = get_vault_path()
    server = ThreadingHTTPServer(("localhost", PORT), Handler)
    print(f"Serving on http://localhost:{PORT} (vault: {VAULT_ROOT})")
    webbrowser.open(f"http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
```

- [ ] **Step 2: 末尾の `if __name__ == "__main__":` ブロックをTask 2の仮実装から差し替え**

```python
if __name__ == "__main__":
    main()
```

（Task 2 Step 1で書いた `vault_root = get_vault_path(); notes = scan_vault(...); print(...)` の3行は削除し、上記の1行に置き換える）

- [ ] **Step 3: サーバーを起動して動作確認（バックグラウンド実行）**

Run: `./venv/bin/python web/server.py &`
Expected: `Serving on http://localhost:8765 (vault: ...)` が表示され、ブラウザが自動で開く（この時点では`index.html`が無いので404ページが表示されるのが正しい）

- [ ] **Step 4: APIエンドポイントをcurlで確認**

Run: `curl -s http://localhost:8765/api/obsidian/facets | python3 -m json.tool`
Expected: `type`/`category`/`status`/`tags`/`vault_name`（`"脳"`）を含むJSONが返る

Run: `curl -s "http://localhost:8765/api/obsidian/notes?category=instagram&status=active" | python3 -m json.tool`
Expected: 条件に一致するノートのJSON配列が返る

- [ ] **Step 5: サーバーを停止**

Run: `kill %1`（Step 3でバックグラウンド起動したジョブを終了する）

---

### Task 4: obsidian.html（検索・一覧UI）

**Files:**
- Create: `web/obsidian.html`

**Interfaces:**
- Consumes: `GET /api/obsidian/facets`, `GET /api/obsidian/notes?...`（Task 3で実装済み）

- [ ] **Step 1: obsidian.htmlを作成**

```html
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>Obsidian Properties検索</title>
<style>
  body { font-family: -apple-system, sans-serif; margin: 2rem; color: #222; }
  h1 { font-size: 1.4rem; }
  .filters { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
  .filters label { display: flex; flex-direction: column; font-size: 0.85rem; gap: 0.25rem; }
  select, input { padding: 0.4rem; font-size: 0.9rem; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 2rem; }
  th, td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; font-size: 0.85rem; vertical-align: top; }
  th { background: #f5f5f5; }
  tr.preview-row td { background: #fafafa; color: #555; }
  .tag-pill { display: inline-block; background: #eef; border-radius: 3px; padding: 0.1rem 0.4rem; margin-right: 0.25rem; font-size: 0.75rem; }
  .group-title { margin-top: 2rem; font-size: 1.1rem; }
  a.open-link { font-size: 0.8rem; }
</style>
</head>
<body>
<h1>Obsidian Properties検索</h1>

<div class="filters">
  <label>type
    <select id="filter-type"><option value="">すべて</option></select>
  </label>
  <label>category
    <select id="filter-category"><option value="">すべて</option></select>
  </label>
  <label>status
    <select id="filter-status"><option value="">すべて</option></select>
  </label>
  <label>tags（カンマ区切り、AND検索）
    <input id="filter-tags" type="text" placeholder="instagram,knowhow">
  </label>
</div>

<h2 class="group-title">Propertiesありノート</h2>
<table id="table-with-props">
  <thead><tr><th>タイトル</th><th>type</th><th>category</th><th>status</th><th>tags</th><th></th></tr></thead>
  <tbody></tbody>
</table>

<h2 class="group-title">Properties未設定ノート</h2>
<table id="table-without-props">
  <thead><tr><th>タイトル</th><th></th></tr></thead>
  <tbody></tbody>
</table>

<script>
let vaultName = "";

async function loadFacets() {
  const res = await fetch("/api/obsidian/facets");
  const facets = await res.json();
  vaultName = facets.vault_name;
  fillSelect("filter-type", facets.type);
  fillSelect("filter-category", facets.category);
  fillSelect("filter-status", facets.status);
}

function fillSelect(id, values) {
  const select = document.getElementById(id);
  for (const value of values) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = value;
    select.appendChild(opt);
  }
}

function openLink(note) {
  const params = new URLSearchParams({
    vault: vaultName,
    file: note.path.replace(/\.md$/, ""),
  });
  return `obsidian://open?${params.toString()}`;
}

function renderTables(notes) {
  const withProps = notes.filter(n => n.type || n.category || n.status || (n.tags && n.tags.length));
  const withoutProps = notes.filter(n => !n.type && !n.category && !n.status && (!n.tags || !n.tags.length));

  const bodyWith = document.querySelector("#table-with-props tbody");
  bodyWith.innerHTML = "";
  for (const note of withProps) {
    const row = document.createElement("tr");
    const tagsHtml = (note.tags || []).map(t => `<span class="tag-pill">${t}</span>`).join("");
    row.innerHTML = `
      <td>${note.title}</td>
      <td>${note.type || ""}</td>
      <td>${note.category || ""}</td>
      <td>${note.status || ""}</td>
      <td>${tagsHtml}</td>
      <td><a class="open-link" href="${openLink(note)}">Obsidianで開く</a></td>
    `;
    row.style.cursor = "pointer";
    row.addEventListener("click", (e) => {
      if (e.target.tagName === "A") return;
      togglePreview(row, note);
    });
    bodyWith.appendChild(row);
  }

  const bodyWithout = document.querySelector("#table-without-props tbody");
  bodyWithout.innerHTML = "";
  for (const note of withoutProps) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${note.title}</td>
      <td><a class="open-link" href="${openLink(note)}">Obsidianで開く</a></td>
    `;
    bodyWithout.appendChild(row);
  }
}

function togglePreview(row, note) {
  const next = row.nextElementSibling;
  if (next && next.classList.contains("preview-row")) {
    next.remove();
    return;
  }
  const previewRow = document.createElement("tr");
  previewRow.className = "preview-row";
  const td = document.createElement("td");
  td.colSpan = 6;
  td.textContent = note.preview || "(本文なし)";
  previewRow.appendChild(td);
  row.after(previewRow);
}

async function loadNotes() {
  const params = new URLSearchParams();
  const type = document.getElementById("filter-type").value;
  const category = document.getElementById("filter-category").value;
  const status = document.getElementById("filter-status").value;
  const tags = document.getElementById("filter-tags").value;
  if (type) params.set("type", type);
  if (category) params.set("category", category);
  if (status) params.set("status", status);
  if (tags) params.set("tag", tags);

  const res = await fetch(`/api/obsidian/notes?${params.toString()}`);
  const notes = await res.json();
  renderTables(notes);
}

for (const id of ["filter-type", "filter-category", "filter-status"]) {
  document.getElementById(id).addEventListener("change", loadNotes);
}
document.getElementById("filter-tags").addEventListener("input", () => {
  clearTimeout(window._tagDebounce);
  window._tagDebounce = setTimeout(loadNotes, 300);
});

loadFacets().then(loadNotes);
</script>
</body>
</html>
```

- [ ] **Step 2: サーバーを起動してブラウザで動作確認**

Run: `./venv/bin/python web/server.py`
Expected（`http://localhost:8765/obsidian.html` を手動で開いて確認）:
- type/category/statusのプルダウンに実際の値（`instagram`, `video`, `sns`, `obsidian`, `learning`など）が入っている
- 何もフィルタしない状態で「Propertiesありノート」に約24件、「Properties未設定ノート」に`TODO`と`USJ 朝並ぶ`の2件が出る
- `category`を`instagram`に絞ると該当ノートだけになる
- `tags`欄に`instagram,knowhow`と入れるとAND検索で絞り込まれる
- 行をクリックすると本文プレビューが展開/折りたたみされる
- 「Obsidianで開く」リンクのURLが `obsidian://open?vault=%E8%84%B3&file=...` の形式になっている（実際にクリックしてObsidianアプリが起動し、該当ノートが開くことも確認する）

- [ ] **Step 3: サーバーを停止**

Ctrl+Cでサーバーを停止する

---

### Task 5: index.html（ダッシュボード入口）

**Files:**
- Create: `web/index.html`

**Interfaces:**
- Consumes: なし（静的リンクのみ）
- Produces: `/` へのアクセスでこのページが表示される（Task 3の`_serve_file(WEB_DIR / "index.html", ...)`が依存）

- [ ] **Step 1: index.htmlを作成**

```html
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>ダッシュボード</title>
<style>
  body { font-family: -apple-system, sans-serif; margin: 2rem; }
  ul { line-height: 2; }
</style>
</head>
<body>
<h1>ローカルダッシュボード</h1>
<ul>
  <li><a href="/obsidian.html">Obsidian Properties検索</a></li>
</ul>
</body>
</html>
```

（将来Instagram用のUIができたら、ここにリンクを追加する）

- [ ] **Step 2: 動作確認**

Run: `./venv/bin/python web/server.py`
Expected: ブラウザが自動で開き、`http://localhost:8765/` に「Obsidian Properties検索」へのリンクが1つ表示される。クリックすると`obsidian.html`に遷移し、Task 4で確認した挙動が動く

Ctrl+Cでサーバーを停止する

---

### Task 6: README更新・最終通し確認

**Files:**
- Modify: `README.md`（「ディレクトリ構成」と「クイックスタート」にobsidian_ui関連の記述を追加）

**Interfaces:**
- Consumes: Task 1〜5で作成した全ファイル
- Produces: なし（ドキュメント更新のみ）

- [ ] **Step 1: README.mdの「ディレクトリ構成」セクションに`web/`を追記**

`## ディレクトリ構成` のコードブロック内、`└── logs/` ブロックの後（末尾の \`\`\` の直前）に以下を追加する:

```
└── web/
    ├── server.py          # ローカルダッシュボード用HTTPサーバ(Obsidian Properties検索など)
    ├── index.html          # ダッシュボード入口
    └── obsidian.html       # Obsidian VaultのProperties検索UI
```

- [ ] **Step 2: README.mdの「クイックスタート」セクションに起動コマンドを追記**

`### 自分でコマンドを打つ場合` のコードブロック内に以下を追加する:

```bash
# Obsidian VaultのProperties検索UIを起動(ブラウザが自動で開く)
./venv/bin/python web/server.py
```

- [ ] **Step 3: スペックに記載した確認項目を通しで実行**

Run: `./venv/bin/python web/server.py`

以下をブラウザ（`http://localhost:8765`）で一通り確認する（`docs/superpowers/specs/2026-09-24-obsidian-properties-ui-design.md` のテスト方針セクションと同一）:
- [ ] facetsのプルダウンに実際の値（instagram/video/sns/obsidian/learning等）が出ること
- [ ] type/category/status/tagsそれぞれの単独フィルタが正しく絞り込めること
- [ ] type+category+statusの組み合わせフィルタが正しく絞り込めること
- [ ] Properties未設定のノート（TODO.md、USJ 朝並ぶ.md）が別枠に表示されること
- [ ] 「Obsidianで開く」リンクでObsidianアプリが起動し該当ノートが開くこと

Ctrl+Cでサーバーを停止する。すべて確認できたら完了。
