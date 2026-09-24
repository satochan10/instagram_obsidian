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
