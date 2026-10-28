"""Markdown の記事を WordPress に【下書き】で入れる（公開はしない）。

使い方:
  python3 scripts/wp_draft.py drafts/my-article.md            # 試し（何も送らない）
  python3 scripts/wp_draft.py drafts/my-article.md --go       # 下書きとして送る
  python3 scripts/wp_draft.py drafts/my-article.md --go --update 123   # 下書き123を上書き
  python3 scripts/wp_draft.py drafts/my-article.md --go --upload-images  # 記事内のローカル画像も送る

必要な .env: WP_URL / WP_USER / WP_APP_PASSWORD（アプリケーションパスワード）
状態は必ず draft。公開・予約投稿はこのスクリプトではしません（人が画面で行う）。
"""
from __future__ import annotations

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401


import argparse
import base64
import json
import mimetypes
import os
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import (as_json, first_h1, http, load_env, md_to_html, missing,  # noqa: E402
                    split_front_matter, strip_h1)


def auth_header() -> dict:
    token = f"{os.environ['WP_USER']}:{os.environ['WP_APP_PASSWORD'].replace(' ', '')}"
    return {"Authorization": "Basic " + base64.b64encode(token.encode()).decode()}


def api(path: str) -> str:
    return os.environ["WP_URL"].rstrip("/") + "/wp-json/wp/v2" + path


def local_images(md: str, base: pathlib.Path) -> list[pathlib.Path]:
    found = []
    for src in re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", md):
        if src.startswith(("http://", "https://")):
            continue
        p = (base / src).resolve()
        if p.exists():
            found.append(p)
    return found


def upload_image(p: pathlib.Path) -> str | None:
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    # filename は英数字の名前、filename* は元の名前（日本語の名前でも送れるように両方付ける）
    plain = p.name if p.name.isascii() else "image" + p.suffix
    name = urllib.parse.quote(p.name)
    h = auth_header()
    h.update({"Content-Type": ctype,
              "Content-Disposition": f"attachment; filename=\"{plain}\"; filename*=UTF-8''{name}"})
    st, _, body = http("POST", api("/media"), h, p.read_bytes(), timeout=120)
    j = as_json(body) or {}
    if st in (200, 201):
        return j.get("source_url")
    print(f"  画像の送信に失敗 {p.name}: {st} {j.get('message', body[:200])}")
    return None


def to_ids(v) -> list[int]:
    if not v:
        return []
    if isinstance(v, str):
        v = [x for x in v.split(",")]
    return [int(x) for x in v if str(x).strip().isdigit()]


def main() -> int:
    ap = argparse.ArgumentParser(description="WordPress に下書きを入れる")
    ap.add_argument("file")
    ap.add_argument("--go", action="store_true", help="実際に送る（付けなければ試しだけ）")
    ap.add_argument("--update", type=int, help="既存の下書きIDを上書きする")
    ap.add_argument("--upload-images", action="store_true", help="記事内のローカル画像をメディアに送る")
    a = ap.parse_args()

    load_env()
    path = pathlib.Path(a.file)
    meta, md = split_front_matter(path.read_text(encoding="utf-8"))
    title = str(meta.get("title") or first_h1(md) or path.stem)
    body_md = strip_h1(md)
    imgs = local_images(body_md, path.parent)

    payload = {
        "title": title,
        "status": "draft",
        "content": md_to_html(body_md),
    }
    if meta.get("slug"):
        payload["slug"] = str(meta["slug"])
    if meta.get("excerpt"):
        payload["excerpt"] = str(meta["excerpt"])
    if to_ids(meta.get("category_ids")):
        payload["categories"] = to_ids(meta.get("category_ids"))
    if to_ids(meta.get("tag_ids")):
        payload["tags"] = to_ids(meta.get("tag_ids"))

    print(f"タイトル: {title}")
    print(f"状態: draft（固定）／ 本文 {len(payload['content'])} 字の HTML")
    print(f"スラッグ: {payload.get('slug', '(WordPress に任せる)')}")
    print(f"カテゴリID: {payload.get('categories', [])} ／ タグID: {payload.get('tags', [])}")
    print(f"ローカル画像: {len(imgs)} 枚" + ("（--upload-images で送る）" if imgs and not a.upload_images else ""))
    if not a.go:
        print("\n[試し] 何も送っていません。送るときは --go を付けてください。")
        print("先頭300字:\n" + payload["content"][:300])
        return 0

    lack = missing("WP_URL", "WP_USER", "WP_APP_PASSWORD")
    if lack:
        print("止めました: .env に足りない項目 → " + ", ".join(lack))
        return 2
    if not os.environ["WP_URL"].startswith("https://") and os.environ.get("WP_ALLOW_HTTP") != "1":
        print("止めました: WP_URL が https ではありません（パスワードが暗号化されずに流れます）。")
        return 2

    if a.update:
        st, _, body = http("GET", api(f"/posts/{a.update}?context=edit"), auth_header())
        cur = as_json(body) or {}
        if st != 200:
            print(f"止めました: 投稿 {a.update} を読めません {st} {cur.get('message', '')}")
            return 1
        if cur.get("status") not in ("draft", "pending", "auto-draft"):
            print(f"止めました: 投稿 {a.update} は状態が {cur.get('status')} です。公開済みは上書きしません。")
            return 1

    if a.upload_images and imgs:
        for p in imgs:
            url = upload_image(p)
            if url:
                rel = os.path.relpath(p, path.parent)
                payload["content"] = payload["content"].replace(f'src="{rel}"', f'src="{url}"')
                print(f"  画像を送りました {p.name} → {url}")

    target = api(f"/posts/{a.update}") if a.update else api("/posts")
    h = auth_header()
    h["Content-Type"] = "application/json"
    st, _, body = http("POST", target, h, json.dumps(payload).encode("utf-8"))
    j = as_json(body) or {}
    if st not in (200, 201):
        print(f"失敗: {st} {j.get('code', '')} {j.get('message', body[:300])}")
        return 1
    pid = j.get("id")
    print(f"下書きにしました: ID {pid}")
    print("編集画面: " + os.environ["WP_URL"].rstrip("/") + f"/wp-admin/post.php?post={pid}&action=edit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
