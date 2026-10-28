"""WordPress につながるか確かめ、カテゴリとタグの ID を一覧にする（読むだけ）。

使い方:
  python3 scripts/wp_check.py         # 試し（何も送らない）
  python3 scripts/wp_check.py --go    # 実際に読みに行く
"""
from __future__ import annotations

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401


import argparse
import base64
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import as_json, http, load_env, missing  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", action="store_true")
    a = ap.parse_args()
    load_env()
    base = os.environ.get("WP_URL", "https://example.com").rstrip("/") + "/wp-json/wp/v2"
    steps = [("ログインの確認", "/users/me?context=edit"),
             ("カテゴリ", "/categories?per_page=100"),
             ("タグ", "/tags?per_page=100")]
    if not a.go:
        print("[試し] 次を読みに行きます（--go で実行）:")
        for name, p in steps:
            print(f"  GET {base}{p}  … {name}")
        lack = missing("WP_URL", "WP_USER", "WP_APP_PASSWORD")
        print("  .env: " + ("そろっています" if not lack else "足りない → " + ", ".join(lack)))
        return 0
    lack = missing("WP_URL", "WP_USER", "WP_APP_PASSWORD")
    if lack:
        print("止めました: .env に足りない項目 → " + ", ".join(lack))
        return 2
    tok = f"{os.environ['WP_USER']}:{os.environ['WP_APP_PASSWORD'].replace(' ', '')}"
    h = {"Authorization": "Basic " + base64.b64encode(tok.encode()).decode()}
    rc = 0
    for name, p in steps:
        st, _, body = http("GET", base + p, h)
        j = as_json(body)
        if st != 200:
            print(f"{name}: 失敗 {st} {(j or {}).get('message', body[:200]) if isinstance(j, dict) else body[:200]}")
            rc = 1
            continue
        if isinstance(j, dict):
            print(f"{name}: OK（ユーザー名 {j.get('slug')}・権限 {', '.join(j.get('roles', []))}）")
        else:
            print(f"{name}: {len(j)} 件")
            for t in j:
                print(f"  ID {t['id']:>5}  {t['name']}（{t.get('count', 0)} 記事）")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
