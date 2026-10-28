"""Search Console の数字で公開後の振り返りをする（読むだけ）。

出すもの（out/ に Markdown と CSV）:
  - 検索語ごとの 表示回数・クリック・クリック率・平均順位
  - 伸びしろ … 平均順位 8〜20 位で表示回数が多い語（見出し・本文を足すと上がりやすい）
  - タイトルの直し候補 … 表示は多いのにクリック率が低い語

使い方:
  python3 scripts/gsc_report.py                              # 試し（何も送らない・送る中身を出す）
  python3 scripts/gsc_report.py --go                         # 直近28日・サイト全体
  python3 scripts/gsc_report.py --go --page https://example.com/my-article/   # 1記事だけ
  python3 scripts/gsc_report.py --go --days 90

必要な .env: GSC_SITE_URL / GSC_CLIENT_ID / GSC_CLIENT_SECRET / GSC_REFRESH_TOKEN
GSC_SITE_URL は Search Console に登録した形のまま（例 https://example.com/ や sc-domain:example.com）。
"""
from __future__ import annotations

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401


import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import OUT, as_json, http, load_env, missing  # noqa: E402

TOKEN = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"


def access_token() -> str | None:
    body = urllib.parse.urlencode({
        "client_id": os.environ["GSC_CLIENT_ID"], "client_secret": os.environ["GSC_CLIENT_SECRET"],
        "refresh_token": os.environ["GSC_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
    st, _, b = http("POST", TOKEN, {"Content-Type": "application/x-www-form-urlencoded"}, body)
    j = as_json(b) or {}
    if st != 200:
        print(f"鍵の更新に失敗: {st} {j.get('error')} {j.get('error_description', '')}")
        return None
    return j["access_token"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--page", help="この URL だけに絞る")
    ap.add_argument("--rows", type=int, default=1000)
    a = ap.parse_args()
    load_env()

    end = dt.date.today() - dt.timedelta(days=3)  # 確定した数字だけ使うため数日あける
    start = end - dt.timedelta(days=a.days - 1)
    req = {"startDate": start.isoformat(), "endDate": end.isoformat(),
           "dimensions": ["query", "page"], "rowLimit": max(1, min(a.rows, 25000))}
    if a.page:
        req["dimensionFilterGroups"] = [{"filters": [
            {"dimension": "page", "operator": "equals", "expression": a.page}]}]
    site = os.environ.get("GSC_SITE_URL", "https://example.com/")
    url = API.format(site=urllib.parse.quote(site, safe=""))
    if not a.go:
        print("[試し] 次を送ります（--go で実行）:")
        print("  POST " + url)
        print("  " + json.dumps(req, ensure_ascii=False))
        lack = missing("GSC_SITE_URL", "GSC_CLIENT_ID", "GSC_CLIENT_SECRET", "GSC_REFRESH_TOKEN")
        print("  .env: " + ("そろっています" if not lack else "足りない → " + ", ".join(lack)))
        return 0
    lack = missing("GSC_SITE_URL", "GSC_CLIENT_ID", "GSC_CLIENT_SECRET", "GSC_REFRESH_TOKEN")
    if lack:
        print("止めました: .env に足りない項目 → " + ", ".join(lack))
        return 2
    tok = access_token()
    if not tok:
        return 1
    st, _, b = http("POST", url, {"Authorization": "Bearer " + tok, "Content-Type": "application/json"},
                    json.dumps(req).encode())
    j = as_json(b) or {}
    if st != 200:
        print(f"失敗: {st} {j.get('error', {}).get('message', b[:300])}")
        return 1
    rows = j.get("rows", [])
    print(f"{start}〜{end} ／ {len(rows)} 行")

    OUT.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    cpath = OUT / f"gsc-{stamp}.csv"
    with cpath.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["query", "page", "clicks", "impressions", "ctr", "position"])
        for r in rows:
            w.writerow(r["keys"] + [r["clicks"], r["impressions"], round(r["ctr"], 4), round(r["position"], 1)])

    nobi = sorted([r for r in rows if 8 <= r["position"] <= 20], key=lambda r: -r["impressions"])[:20]
    imps = sorted(r["impressions"] for r in rows)
    mid = imps[len(imps) // 2] if imps else 0
    title_fix = sorted([r for r in rows if r["impressions"] >= max(mid, 50) and r["ctr"] < 0.02],
                       key=lambda r: -r["impressions"])[:20]

    def line(r):
        return (f"| {r['keys'][0]} | {r['impressions']} | {r['clicks']} | {r['ctr'] * 100:.1f}% | "
                f"{r['position']:.1f} | {r['keys'][1]} |")

    head = "| 検索語 | 表示 | クリック | クリック率 | 平均順位 | ページ |\n|---|---|---|---|---|---|"
    md = [f"# Search Console 振り返り（{start}〜{end}）", "",
          f"- 対象: {a.page or 'サイト全体'}", f"- 行数: {len(rows)}（数え方: 検索語×ページ）", "",
          "## 伸びしろ（平均 8〜20 位・表示の多い順）", head] + [line(r) for r in nobi] + [
          "", "## タイトル・説明文の直し候補（表示が多いのにクリック率 2% 未満）", head] + [
          line(r) for r in title_fix] + ["", f"元の数字: {cpath.name}"]
    mpath = OUT / f"gsc-{stamp}.md"
    mpath.write_text("\n".join(md), encoding="utf-8")
    print(f"書き出し: {mpath}\n         {cpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
