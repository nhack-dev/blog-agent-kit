"""Markdown の記事を note に貼りやすい形に整える（手元にファイルを作るだけ）。

note には一般に公開された投稿用の API がありません。このキットは note へ自動では投稿しません。
できたファイルを開き、note のエディタに人が貼り付けて下書き保存してください。

使い方:
  python3 scripts/note_draft.py drafts/my-article.md
  → out/note/<名前>.txt（本文）と out/note/<名前>-images.txt（差し込む画像の一覧）
"""
from __future__ import annotations

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401


import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import OUT, first_h1, split_front_matter, strip_h1  # noqa: E402


def convert(md: str) -> tuple[str, list[str]]:
    images: list[str] = []
    lines = []
    for line in md.split("\n"):
        m = re.match(r"^\s*!\[([^\]]*)\]\(([^)\s]+)\)\s*$", line)
        if m:
            images.append(m.group(2))
            lines.append(f"［画像{len(images)}を差し込む：{m.group(1) or m.group(2)}］")
            continue
        # note のエディタは「## 」で大見出し、「### 」で小見出しになる（入力のショートカット）
        line = re.sub(r"^####\s+", "### ", line)
        line = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r"\1 \2", line)  # リンクは URL を並べる
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return text, images


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    a = ap.parse_args()
    path = pathlib.Path(a.file)
    meta, md = split_front_matter(path.read_text(encoding="utf-8"))
    title = str(meta.get("title") or first_h1(md) or path.stem)
    text, images = convert(strip_h1(md))
    if meta.get("affiliate") or meta.get("pr"):
        if not re.search(r"広告|PR|プロモーション", text[:200]):
            text = "※この記事は広告（PR）を含みます。\n\n" + text
    d = OUT / "note"
    d.mkdir(parents=True, exist_ok=True)
    stem = str(meta.get("slug") or path.stem)
    (d / f"{stem}.txt").write_text(f"タイトル：{title}\n\n" + text, encoding="utf-8")
    (d / f"{stem}-images.txt").write_text("\n".join(f"画像{i + 1}: {s}" for i, s in enumerate(images)) + "\n",
                                          encoding="utf-8")
    print(f"できました: {d / (stem + '.txt')}（{len(text)}字・画像 {len(images)} 枚）")
    print("note への投稿は人が行います（自動では投稿しません）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
