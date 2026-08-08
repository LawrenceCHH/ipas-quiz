#!/usr/bin/env python3
"""Rebuild index.html's embedded POOL constant from subjects/*/*.json.

subjects/*/*.json (`verified_question_pool`) is the system of record. This
script merges every json under subjects/, validates it, and rewrites line
378 of index.html (the `const POOL = [...]` literal) to match. It never
touches any other line of index.html.

Usage:
    uv run --project tools python tools/build_pool.py            # write
    uv run --project tools python tools/build_pool.py --check    # dry run

See project.md, section "階段一 實作計畫 / 6. build_pool.py 設計" for the
full spec this implements (including the C2/C3 corrections in section C).
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "index.html"

# subjects/<dir> -> subject_code, used only to backfill questions whose json
# entry (or whole file) is missing subject_code. 1-ai/progress.json doesn't
# even have a top-level subject_code, so this has to be a directory lookup,
# not something read from the file itself.
DIR_TO_SUBJECT = {
    "1-ai": "s1",
    "2-bigdata": "s2",
    "3-ml": "s3",
    "entry-1-ai": "e1",
    "entry-2-genai": "e2",
}

VALID_SUBJECTS = {"s1", "s2", "s3", "e1", "e2"}
SUBJECT_LEVEL = {
    "s1": "intermediate", "s2": "intermediate", "s3": "intermediate",
    "e1": "entry", "e2": "entry",
}
SUBJECT_ORDER = {"s1": 0, "s2": 1, "s3": 2, "e1": 3, "e2": 4}
LEVEL_ORDER = {"intermediate": 0, "entry": 1}

# Source-category rank within a subject: official test questions before
# AI-generated supplementary questions. exam-*/entry-* are official past
# exam questions, sample-* are official sample questions, gen-*/guide-* are
# AI-generated.
CATEGORY_RANK = {"exam": 0, "entry": 0, "sample": 1, "gen": 2, "guide": 2}

REQUIRED_KEYS = ["id", "topic", "question_text", "options", "correct_answer",
                  "source", "explanation"]

_ID_PREFIX_RE = re.compile(r"^([a-zA-Z]+)-")
_NATSORT_RE = re.compile(r"(\d+)")


def natsort_key(s: str):
    return [int(t) if t.isdigit() else t for t in _NATSORT_RE.split(s)]


def category_of(id_: str) -> int:
    m = _ID_PREFIX_RE.match(id_)
    prefix = m.group(1) if m else id_
    return CATEGORY_RANK.get(prefix, 99)


def sort_key(q: dict):
    sc = q.get("subject_code", "")
    level = SUBJECT_LEVEL.get(sc, "zzz")
    return (
        LEVEL_ORDER.get(level, 9),
        SUBJECT_ORDER.get(sc, 9),
        category_of(q["id"]),
        natsort_key(q["id"]),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

class LoadResult:
    def __init__(self):
        self.all_questions: list[dict] = []       # every question, verified or not
        self.subject_code_filled: list[str] = []  # ids that got subject_code backfilled
        self.file_of: dict[str, str] = {}          # id -> source json path (repo-relative)


def load_all(repo_root: Path) -> LoadResult:
    result = LoadResult()
    json_paths = sorted(glob.glob(str(repo_root / "subjects" / "*" / "*.json")))
    for jp in json_paths:
        jp_path = Path(jp)
        rel = jp_path.relative_to(repo_root).as_posix()
        subject_dir = jp_path.parent.name
        dir_subject_code = DIR_TO_SUBJECT.get(subject_dir)
        data = json.loads(jp_path.read_text(encoding="utf-8"))
        questions = data.get("verified_question_pool", [])
        for q in questions:
            if not q.get("subject_code"):
                if dir_subject_code is None:
                    raise SystemExit(
                        f"ERROR: {rel}: question {q.get('id')!r} has no "
                        f"subject_code and directory {subject_dir!r} isn't in "
                        f"DIR_TO_SUBJECT"
                    )
                q["subject_code"] = dir_subject_code
                result.subject_code_filled.append(q.get("id"))
            result.all_questions.append(q)
            result.file_of[q.get("id")] = rel
    return result


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

class ValidationReport:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)


EXPL_TITLE_RE = re.compile(r"\*\*為什麼\s+[A-D]\s+是")
MERGED_BULLET_RE = re.compile(r"^(\s*-\s+)((?:[A-D]\.?\s*/\s*)+[A-D])\.", re.MULTILINE)


def validate(all_questions: list[dict], report: ValidationReport, repo_root: Path):
    # id uniqueness across ALL questions (verified or not)
    seen: dict[str, int] = {}
    for q in all_questions:
        qid = q.get("id")
        seen[qid] = seen.get(qid, 0) + 1
    dups = sorted(k for k, v in seen.items() if v > 1)
    if dups:
        report.error(f"重複 id（跨全部 json）: {dups}")

    for q in all_questions:
        qid = q.get("id", "<no id>")
        if not q.get("verified"):
            continue  # unverified drafts are only checked for id uniqueness above

        # required keys
        missing = [k for k in REQUIRED_KEYS if k not in q or q[k] is None]
        if missing:
            report.error(f"{qid}: 缺必填欄位 {missing}")
            continue

        # options
        opts = q["options"]
        if not isinstance(opts, dict) or set(opts.keys()) != {"A", "B", "C", "D"}:
            report.error(f"{qid}: options 的 key 不是剛好 {{A,B,C,D}}: {sorted(opts.keys()) if isinstance(opts, dict) else opts!r}")
        else:
            empty = [k for k, v in opts.items() if not v or not str(v).strip()]
            if empty:
                report.error(f"{qid}: options 有空值: {empty}")

        # correct_answer
        if isinstance(opts, dict) and q.get("correct_answer") not in opts:
            report.error(f"{qid}: correct_answer {q.get('correct_answer')!r} 不在 options 的 key 裡")

        # subject_code
        if q.get("subject_code") not in VALID_SUBJECTS:
            report.error(f"{qid}: subject_code {q.get('subject_code')!r} 不在 {sorted(VALID_SUBJECTS)}")

        # source
        src = q.get("source") or {}
        sfile = src.get("file")
        spage = src.get("page")
        if not sfile:
            report.error(f"{qid}: source.file 缺")
        elif not (sfile.startswith("http://") or sfile.startswith("https://")):
            # C2: only local paths get an existence check; URLs are format-only
            if not (repo_root / sfile).exists():
                report.error(f"{qid}: source.file 找不到檔案: {sfile}")
        if spage is None or (isinstance(spage, (int, float)) and spage < 1):
            report.error(f"{qid}: source.page 無效: {spage!r}")

        # image
        img = q.get("image")
        if img:
            if not (repo_root / img).exists():
                report.error(f"{qid}: image 找不到檔案: {img}")

        # explanation format
        expl = q.get("explanation") or ""
        if not EXPL_TITLE_RE.search(expl):
            report.error(f"{qid}: explanation 缺 '**為什麼 X 是' 標題（字母前後要有空白）")
        if "記憶要點" not in expl:
            report.error(f"{qid}: explanation 缺「記憶要點」段")
        # C3: merged "- A/B." bullets are now safely handled by
        # translateExplanation()'s Pass 2/3 (17fa64e) — downgrade to warning.
        if MERGED_BULLET_RE.search(expl):
            report.warn(f"{qid}: explanation 有合併字母 bullet（- A/B. 形式）— 允許但建議新題改用單字母")

        # length-tell warning: only for generated:true questions
        if q.get("generated") is True:
            longest_distractor = max(
                (len(v) for k, v in opts.items() if k != q.get("correct_answer")),
                default=0,
            )
            correct_len = len(opts.get(q.get("correct_answer"), ""))
            if correct_len - longest_distractor >= 3:
                sc = q.get("subject_code")
                if sc in ("e1", "e2"):
                    report.warn(f"{qid}: 選項長度 tell（已知豁免、不修，entry 兩科 guide-* 已知問題）")
                else:
                    report.warn(f"{qid}: 選項長度 tell（正解比最長干擾項長 >=3 字）")


# ---------------------------------------------------------------------------
# index.html POOL <-> json helpers
# ---------------------------------------------------------------------------

def extract_pool_from_html(html_src: str):
    """Return (list_of_question_dicts, line_start, line_end_exclusive) for
    the `const POOL = [...]` literal on its line in index.html."""
    marker = "const POOL = ["
    start = html_src.index(marker) + len("const POOL = ")
    depth = 0
    j = start
    instr = False
    esc = False
    while j < len(html_src):
        c = html_src[j]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
        else:
            if c == '"':
                instr = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    break
        j += 1
    array_end = j + 1  # index just past the closing ]
    pool = json.loads(html_src[start:array_end])
    # locate the full line boundaries for a byte-for-byte single-line replace
    line_start = html_src.rindex("\n", 0, html_src.index(marker)) + 1
    line_end = html_src.index("\n", array_end)
    return pool, line_start, line_end


def dump_question(q: dict) -> str:
    return json.dumps(q, ensure_ascii=False, separators=(",", ": "))


def build_pool_line(questions: list[dict]) -> str:
    body = ",".join(dump_question(q) for q in questions)
    return "const POOL = [" + body + "];"


# ---------------------------------------------------------------------------
# Diff (for --check and for human-readable summaries)
# ---------------------------------------------------------------------------

COMPARE_FIELDS = ["topic", "question_text", "options", "correct_answer",
                   "source", "explanation", "image", "verified", "subject_code"]


def diff_pools(old_by_id: dict, new_by_id: dict):
    only_old = sorted(set(old_by_id) - set(new_by_id))
    only_new = sorted(set(new_by_id) - set(old_by_id))
    field_diff_ids = {f: [] for f in COMPARE_FIELDS}
    for qid in sorted(set(old_by_id) & set(new_by_id)):
        o, n = old_by_id[qid], new_by_id[qid]
        for f in COMPARE_FIELDS:
            if o.get(f) != n.get(f):
                field_diff_ids[f].append(qid)
    return only_old, only_new, field_diff_ids


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                     help="recompute but don't write; exit 1 if index.html POOL is out of sync with JSON")
    args = ap.parse_args()

    load_result = load_all(REPO_ROOT)
    all_questions = load_result.all_questions

    report = ValidationReport()
    validate(all_questions, report, REPO_ROOT)

    if report.errors:
        print(f"VALIDATION FAILED: {len(report.errors)} error(s)")
        for e in report.errors:
            print(f"  ERROR: {e}")
        for w in report.warnings:
            print(f"  WARN:  {w}")
        sys.exit(1)

    verified = [q for q in all_questions if q.get("verified") is True]
    skipped = [q for q in all_questions if q.get("verified") is not True]
    verified_sorted = sorted(verified, key=sort_key)
    new_by_id = {q["id"]: q for q in verified_sorted}

    html_src = INDEX_HTML.read_text(encoding="utf-8")
    old_pool, line_start, line_end = extract_pool_from_html(html_src)
    old_by_id = {q["id"]: q for q in old_pool}

    only_old, only_new, field_diff_ids = diff_pools(old_by_id, new_by_id)

    in_sync = not only_old and not only_new and not any(field_diff_ids.values())

    print(f"讀到 {len(all_questions)} 題（跨 {len(set(load_result.file_of.values()))} 個 json 檔）")
    print(f"subject_code 自動補齊: {len(load_result.subject_code_filled)} 題")
    print(f"verified=true: {len(verified)} 題 ／ 跳過（未驗證）: {len(skipped)} 題")
    if skipped:
        by_file = {}
        for q in skipped:
            by_file.setdefault(load_result.file_of.get(q["id"], "?"), []).append(q["id"])
        for f, ids in sorted(by_file.items()):
            print(f"  跳過 {len(ids)} 題 ({f}): {ids[0]} .. {ids[-1]}")
    if report.warnings:
        print(f"\n警告 {len(report.warnings)} 則：")
        for w in report.warnings[:50]:
            print(f"  WARN: {w}")
        if len(report.warnings) > 50:
            print(f"  ... 其餘 {len(report.warnings) - 50} 則省略")

    print(f"\nindex.html 現有 POOL: {len(old_pool)} 題 ／ 重建後 POOL: {len(verified_sorted)} 題")
    print(f"只在 JSON（新 POOL 才有）: {len(only_new)} 題" + (f" {only_new[:10]}{'...' if len(only_new) > 10 else ''}" if only_new else ""))
    print(f"只在現有 POOL（JSON 已無）: {len(only_old)} 題" + (f" {only_old[:10]}{'...' if len(only_old) > 10 else ''}" if only_old else ""))
    for f in COMPARE_FIELDS:
        ids = field_diff_ids[f]
        gen_ids = [i for i in ids if _ID_PREFIX_RE.match(i) and _ID_PREFIX_RE.match(i).group(1) in ("gen", "guide")]
        print(f"  {f:16s} {len(ids)} 題不一致" + (f"（其中 gen/guide-*: {len(gen_ids)}）" if ids else ""))

    if args.check:
        if in_sync:
            print("\n--check: index.html 與 JSON 同步。 exit 0")
            sys.exit(0)
        else:
            print("\n--check: index.html 與 JSON 不同步。 exit 1")
            sys.exit(1)

    # write mode
    new_line = build_pool_line(verified_sorted)
    new_src = html_src[:line_start] + new_line + html_src[line_end:]
    INDEX_HTML.write_text(new_src, encoding="utf-8")
    print(f"\n已寫入 {INDEX_HTML}（只置換 POOL 那一行）")


if __name__ == "__main__":
    main()
