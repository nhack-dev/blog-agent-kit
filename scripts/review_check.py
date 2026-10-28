"""推敲の機械チェック（手元だけで動く・どこにも送らない）。

見るもの:
  1. 長すぎる文・同じ文末の連続
  2. 根拠が要る言い方（No.1・最安・絶対 など）… 景品表示法の優良誤認・有利誤認の入口
  3. 医薬品のような効き目の言い方 … 医薬品医療機器等法（薬機法）の入口
  4. 広告の記事なのに「広告」「PR」等の表示が冒頭に無い … ステルスマーケティング規制の入口
  5. 書きかけの印（[要出典] [要確認] TODO）
  6. 自分の体験の段落があるか
  7. 見出しの並び（H2 の数・H3 だけで H2 が無い 等）

使い方:
  python3 scripts/review_check.py drafts/my-article.md
  python3 scripts/review_check.py drafts/my-article.md --strict   # 要直しがあれば終了コード1

機械で拾えるのは「入口」だけです。拾われなくても法律上問題が無いとは限りません。
最終の判断は playbooks/08-affiliate-and-law.md と人の目で行ってください。
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
from common import split_front_matter  # noqa: E402

# 根拠が無ければ使えない言い方（景品表示法の入口）
KONKYO = ["No.1", "No１", "ナンバーワン", "日本一", "世界一", "業界初", "日本初", "世界初", "業界最安",
          "最安", "最高品質", "最強", "100%", "１００％"]
# 文脈しだいで問題になる言い方（効果の保証・期限や値引きの表示は本当かを確かめる）
YOWAI = ["絶対", "必ず", "確実に", "誰でも", "完全", "永久", "今だけ", "本日限り", "限定", "残りわずか",
         "通常価格", "定価から", "稼げる", "儲かる"]
# 医薬品のような効き目（健康食品・化粧品・雑貨で使うと薬機法の入口）
YAKKI = ["治る", "治す", "治療", "完治", "改善する", "予防", "効く", "効果がある", "効能", "痩せる", "やせる",
         "脂肪燃焼", "若返", "アンチエイジング", "シミが消", "シワが消", "ニキビが治", "薄毛が治", "育毛",
         "発毛", "免疫力", "血圧が下が", "血糖値", "デトックス", "副作用なし", "副作用がない",
         "医師も推奨", "医師が推奨", "医学的に証明", "臨床で証明"]
PR_MARK = re.compile(r"広告|PR|プロモーション|宣伝|アフィリエイト|提供を受け")
TODO = re.compile(r"\[要出典\]|\[要確認\]|TODO|ＴＯＤＯ|〇〇|○○|XXX")
TAIKEN = re.compile(r"体験|やってみ|使ってみ|試してみ|実際に|わたしの場合|私の場合|筆者")


def sentences(text: str) -> list[str]:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    out = []
    for line in text.split("\n"):
        line = line.strip()
        # 見出し・引用・表・箇条書き・番号つきの行は文として数えない
        if not line or re.match(r"^([#>|*-]|\d+\.)", line):
            continue
        line = line.replace("**", "")
        out += [s.strip() for s in re.split(r"(?<=[。！？!?])", line) if s.strip()]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--max-len", type=int, default=80, help="1文の長さの目安（字）")
    a = ap.parse_args()
    meta, md = split_front_matter(pathlib.Path(a.file).read_text(encoding="utf-8"))
    body = md
    need_fix: list[str] = []
    notes: list[str] = []

    # 1. 文の長さ・文末
    ss = sentences(body)
    long_s = [s for s in ss if len(s) > a.max_len]
    for s in long_s[:10]:
        notes.append(f"長い文（{len(s)}字）: {s[:40]}…")
    ends = [re.sub(r"[。！？!?]$", "", s)[-2:] for s in ss]
    for i in range(len(ends) - 2):
        if ends[i] == ends[i + 1] == ends[i + 2]:
            notes.append(f"同じ文末が3回続く「…{ends[i]}」: {ss[i][:30]}…")

    # 2・3. 言い方
    for w in KONKYO:
        n = body.count(w)
        if n:
            need_fix.append(f"根拠が要る言い方「{w}」×{n} … 根拠（調査名・時期・範囲）を横に書くか言い換える")
    for w in YOWAI:
        n = body.count(w)
        if n:
            notes.append(f"「{w}」×{n} … 効果の保証・期限・値引きの意味で使っていないか（本当か・根拠はあるか）")
    for w in YAKKI:
        n = body.count(w)
        if n:
            need_fix.append(f"効き目の言い方「{w}」×{n} … 医薬品でない商品なら言い換える（薬機法）")

    # 4. 広告の表示
    is_ad = bool(meta.get("affiliate")) or bool(meta.get("pr"))
    head = body[:400]
    if is_ad and not PR_MARK.search(head):
        need_fix.append("広告の記事（affiliate: true）なのに冒頭400字に「広告」「PR」等の表示が無い（ステマ規制）")
    if not is_ad and re.search(r"https?://[^\s)]*(?:aff|affiliate|click|track|\?a8|\bref=)", body):
        notes.append("広告のリンクらしいものがあります。広告なら前置きに affiliate: true を書き、冒頭に表示を入れる")

    # 5. 書きかけ
    for m in TODO.finditer(body):
        need_fix.append(f"書きかけの印「{m.group(0)}」が残っている")

    # 6. 体験
    if not TAIKEN.search(body):
        notes.append("自分で試した・使った段落が見当たりません（playbooks/04-review.md の「体験の入れ方」）")

    # 7. 見出し
    h2 = re.findall(r"^##\s+(.+)$", body, re.M)
    h3 = re.findall(r"^###\s+(.+)$", body, re.M)
    if not h2:
        need_fix.append("H2（## 見出し）がありません")
    if h3 and not h2:
        need_fix.append("H3 だけで H2 がありません")
    if len(h2) > 12:
        notes.append(f"H2 が {len(h2)} 個あります。読み手が迷わないか確かめる")

    chars = len(re.sub(r"\s", "", body))
    print(f"文字数 約{chars}字 ／ 文 {len(ss)} ／ H2 {len(h2)} ／ H3 {len(h3)} ／ 広告の記事: {'はい' if is_ad else 'いいえ'}")
    print(f"\n要直し {len(need_fix)} 件")
    for x in need_fix:
        print("  - " + x)
    print(f"\n見てほしい {len(notes)} 件")
    for x in notes:
        print("  - " + x)
    print("\n※ 機械で拾えるのは入口だけです。最終確認は人の目で。")
    return 1 if (a.strict and need_fix) else 0


if __name__ == "__main__":
    raise SystemExit(main())
