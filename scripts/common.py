"""共通の部品：.env の読み込み・HTTP・前置き（front matter）・かんたんな Markdown→HTML 変換。

Python 3.11 の標準ライブラリだけで動きます。
"""
from __future__ import annotations

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401


import html
import json
import os
import pathlib
import re
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
UA = "blog-agent-kit/1.0"


def load_env(path: str | None = None) -> dict:
    """リポジトリ直下の .env を読み、まだ無い環境変数だけ足す。"""
    p = pathlib.Path(path) if path else ROOT / ".env"
    env: dict[str, str] = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in env.items():
        os.environ.setdefault(k, v)
    return env


def missing(*keys: str) -> list[str]:
    return [k for k in keys if not os.environ.get(k)]


def http(method: str, url: str, headers: dict | None = None, body: bytes | None = None,
         timeout: int = 30) -> tuple[int, dict, bytes]:
    """HTTP を1回だけ送る。失敗しても例外にせず (状態コード, ヘッダー, 本文) を返す。"""
    h = {"User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()
    except urllib.error.URLError as e:
        return 0, {}, str(e.reason).encode()
    except Exception as e:  # 切断・時間切れなど
        return 0, {}, f"{type(e).__name__}: {e}".encode()


def as_json(b: bytes):
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:
        return None


# ---------- 前置き（front matter） ----------

def split_front_matter(text: str) -> tuple[dict, str]:
    """先頭の --- で囲んだ部分を key: value として読む（入れ子は扱わない）。"""
    meta: dict[str, object] = {}
    if not text.startswith("---"):
        return meta, text
    parts = text.split("\n")
    end = None
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            end = i
            break
    if end is None:
        return meta, text
    for line in parts[1:end]:
        if ":" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split(":", 1)
        v = v.strip().strip('"').strip("'")
        if v.startswith("[") and v.endswith("]"):
            meta[k.strip()] = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
        elif v.lower() in ("true", "false"):
            meta[k.strip()] = v.lower() == "true"
        else:
            meta[k.strip()] = v
    return meta, "\n".join(parts[end + 1:]).lstrip("\n")


# ---------- Markdown → HTML（記事に要る分だけ） ----------

def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", lambda m: f'<img src="{html.escape(m.group(2))}" alt="{m.group(1)}">', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def md_to_html(md: str) -> str:
    out: list[str] = []
    para: list[str] = []
    lst: list[str] = []
    lst_tag = ""
    in_code = False
    code: list[str] = []
    table: list[str] = []

    def flush_para():
        if para:
            out.append("<p>" + "<br>".join(_inline(x) for x in para) + "</p>")
            para.clear()

    def flush_list():
        nonlocal lst_tag
        if lst:
            out.append(f"<{lst_tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in lst) + f"</{lst_tag}>")
            lst.clear()
            lst_tag = ""

    def flush_table():
        if not table:
            return
        rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in table]
        rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
        if rows:
            head, body = rows[0], rows[1:]
            h = "".join(f"<th>{_inline(c)}</th>" for c in head)
            b = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body)
            out.append(f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>")
        table.clear()

    for raw in md.split("\n"):
        line = raw.rstrip()
        if line.startswith("```"):
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
                code.clear()
                in_code = False
            else:
                flush_para(); flush_list(); flush_table()
                in_code = True
            continue
        if in_code:
            code.append(raw)
            continue
        if line.startswith("|"):
            flush_para(); flush_list()
            table.append(line)
            continue
        flush_table()
        if not line.strip():
            flush_para(); flush_list()
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush_para(); flush_list()
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
            continue
        if re.fullmatch(r"-{3,}|\*{3,}", line.strip()):
            flush_para(); flush_list()
            out.append("<hr>")
            continue
        if line.startswith(">"):
            flush_para(); flush_list()
            out.append(f"<blockquote><p>{_inline(line.lstrip('> ').rstrip())}</p></blockquote>")
            continue
        m = re.match(r"^\s*(?:[-*]|(\d+)\.)\s+(.*)$", line)
        if m:
            flush_para()
            tag = "ol" if m.group(1) else "ul"
            if lst and tag != lst_tag:
                flush_list()
            lst_tag = tag
            lst.append(m.group(2))
            continue
        flush_list()
        para.append(line)
    flush_para(); flush_list(); flush_table()
    if in_code:
        out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
    return "\n".join(out)


def first_h1(md: str) -> str:
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return m.group(1).strip() if m else ""


def strip_h1(md: str) -> str:
    """WordPress はタイトル欄があるので本文の最初の # 見出しを外す。"""
    return re.sub(r"^#\s+.+\n?", "", md, count=1, flags=re.M)
