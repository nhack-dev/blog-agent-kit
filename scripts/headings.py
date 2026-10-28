"""上位記事の見出し（h1〜h3）・タイトル・説明文・おおよその文字数を取り出す。

検索結果そのものは取りに行きません（検索エンジンの自動取得は規約で禁じられていることが多いため）。
上位の URL は、人かエージェントのブラウザ／検索の機能で確かめて urls.txt に書いてください。

使い方:
  python3 scripts/headings.py --file research/urls.txt           # 試し（何も取りに行かない）
  python3 scripts/headings.py --file research/urls.txt --go      # 取りに行く（最大10件・3秒おき）
  python3 scripts/headings.py https://example.com/a https://example.com/b --go

決まり: robots.txt で禁止されたページは読まない／1件ごとに3秒あける／10件まで。
"""
from __future__ import annotations

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401


import argparse
import datetime as dt
import html.parser
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.robotparser

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import OUT, UA, http  # noqa: E402

MAX_URLS = 10
WAIT_SEC = 3


class Grab(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.desc = ""
        self.heads: list[tuple[str, str]] = []
        self._cur: str | None = None
        self._buf: list[str] = []
        self._skip = 0
        self.text_len = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag == "meta" and (a.get("name") or "").lower() == "description":
            self.desc = (a.get("content") or "").strip()
        if tag in ("title", "h1", "h2", "h3"):
            self._cur, self._buf = tag, []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if tag == self._cur:
            t = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if tag == "title":
                self.title = t
            elif t:
                self.heads.append((tag, t))
            self._cur = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._cur:
            self._buf.append(data)
        self.text_len += len(re.sub(r"\s+", "", data))


def allowed(url: str, cache: dict) -> bool:
    u = urllib.parse.urlsplit(url)
    root = f"{u.scheme}://{u.netloc}"
    if root not in cache:
        rp = urllib.robotparser.RobotFileParser()
        st, _, body = http("GET", root + "/robots.txt", timeout=15)
        if st == 200:
            rp.parse(body.decode("utf-8", "replace").splitlines())
        else:
            rp.parse([])  # robots.txt が無ければ全部許可
        cache[root] = rp
    return cache[root].can_fetch(UA, url)


def decode(body: bytes, headers: dict) -> str:
    ct = headers.get("Content-Type", "") or headers.get("content-type", "")
    m = re.search(r"charset=([\w-]+)", ct)
    for enc in ([m.group(1)] if m else []) + ["utf-8", "cp932", "euc_jp"]:
        try:
            return body.decode(enc)
        except Exception:
            continue
    return body.decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--file")
    ap.add_argument("--go", action="store_true")
    a = ap.parse_args()
    urls = list(a.urls)
    if a.file:
        urls += [x.strip() for x in pathlib.Path(a.file).read_text(encoding="utf-8").splitlines()
                 if x.strip().startswith("http")]
    urls = list(dict.fromkeys(urls))
    if len(urls) > MAX_URLS:
        print(f"{len(urls)} 件あります。先頭 {MAX_URLS} 件だけにします。")
        urls = urls[:MAX_URLS]
    if not urls:
        print("URL がありません。--file に1行1URLで書くか、引数で渡してください。")
        return 0 if not a.go else 2
    if not a.go:
        print(f"[試し] 次の {len(urls)} 件を {WAIT_SEC} 秒おきに読みます（--go で実行）:")
        for u in urls:
            print("  " + u)
        return 0

    cache: dict = {}
    rows = []
    for i, u in enumerate(urls):
        if i:
            time.sleep(WAIT_SEC)
        if not allowed(u, cache):
            print(f"とばす（robots.txt で禁止）: {u}")
            rows.append({"url": u, "skipped": "robots"})
            continue
        st, h, body = http("GET", u, {"Accept": "text/html"}, timeout=30)
        if st != 200:
            print(f"読めない {st}: {u}")
            rows.append({"url": u, "skipped": f"http {st}"})
            continue
        g = Grab()
        g.feed(decode(body, h))
        rows.append({"url": u, "title": g.title, "description": g.desc,
                     "chars": g.text_len, "headings": g.heads})
        print(f"読んだ: {u}（見出し {len(g.heads)}・本文 約{g.text_len}字）")

    OUT.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    jpath = OUT / f"headings-{stamp}.json"
    jpath.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# 上位記事の見出し（{stamp}）", ""]
    for r in rows:
        md.append(f"## {r.get('title') or r['url']}")
        md.append(f"- URL: {r['url']}")
        if r.get("skipped"):
            md.append(f"- 読んでいない: {r['skipped']}")
            md.append("")
            continue
        md.append(f"- 説明文: {r.get('description', '')}")
        md.append(f"- 本文 約{r['chars']}字")
        for tag, t in r["headings"]:
            md.append(("  " * (int(tag[1]) - 1)) + f"- {tag.upper()} {t}")
        md.append("")
    mpath = OUT / f"headings-{stamp}.md"
    mpath.write_text("\n".join(md), encoding="utf-8")
    print(f"\n書き出し: {mpath}\n         {jpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
