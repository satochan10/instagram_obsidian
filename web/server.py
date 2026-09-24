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


if __name__ == "__main__":
    main()
