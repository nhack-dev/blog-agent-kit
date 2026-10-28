"""Search Console を読むための鍵（refresh token）を1回だけ取る。

前もって Google Cloud で「OAuth クライアント ID（種類：デスクトップ アプリ）」を作り、
.env に GSC_CLIENT_ID と GSC_CLIENT_SECRET を書いておきます（手順は playbooks/07-after-publish.md）。

使い方:
  python3 scripts/gsc_auth.py          # 試し（何もしない・手順の確認だけ）
  python3 scripts/gsc_auth.py --go     # ブラウザで許可 → 鍵を画面に出す

仕組み: Google の「インストール型アプリ」の形（127.0.0.1 で受け取る・PKCE つき）。
権限は読み取りだけ（webmasters.readonly）。
"""
from __future__ import annotations

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401


import argparse
import base64
import hashlib
import http.server
import json
import os
import pathlib
import secrets
import sys
import threading
import urllib.parse
import webbrowser

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import as_json, http, load_env, missing  # noqa: E402

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", action="store_true")
    a = ap.parse_args()
    load_env()
    lack = missing("GSC_CLIENT_ID", "GSC_CLIENT_SECRET")
    if not a.go:
        print("[試し] --go を付けると次をします:")
        print("  1. 127.0.0.1 の空いている番号で受け口を開く")
        print("  2. ブラウザで Google の許可画面を開く（権限は Search Console の読み取りだけ）")
        print("  3. 戻ってきた合図を鍵（refresh token）に替えて画面に出す → .env の GSC_REFRESH_TOKEN に貼る")
        print("  .env: " + ("そろっています" if not lack else "足りない → " + ", ".join(lack)))
        return 0
    if lack:
        print("止めました: .env に足りない項目 → " + ", ".join(lack))
        return 2

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    got: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("受け取りました。この画面は閉じてかまいません。".encode())

        def log_message(self, *args):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = AUTH + "?" + urllib.parse.urlencode({
        "client_id": os.environ["GSC_CLIENT_ID"], "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    print("ブラウザで次を開いて許可してください（自動で開かないときはコピーして開く）:\n" + url)
    webbrowser.open(url)
    t = threading.Thread(target=srv.handle_request)
    t.start()
    t.join(timeout=300)
    srv.server_close()
    if got.get("state") != state or "code" not in got:
        print("受け取れませんでした: " + json.dumps(got, ensure_ascii=False))
        return 1
    body = urllib.parse.urlencode({
        "code": got["code"], "client_id": os.environ["GSC_CLIENT_ID"],
        "client_secret": os.environ["GSC_CLIENT_SECRET"], "redirect_uri": redirect,
        "grant_type": "authorization_code", "code_verifier": verifier}).encode()
    st, _, b = http("POST", TOKEN, {"Content-Type": "application/x-www-form-urlencoded"}, body)
    j = as_json(b) or {}
    if st != 200 or "refresh_token" not in j:
        print(f"鍵に替えられませんでした: {st} {j}")
        return 1
    print("\n.env に次の1行を足してください（人に見せない・Git に入れない）:")
    print("GSC_REFRESH_TOKEN=" + j["refresh_token"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
