#!/usr/bin/env python3
"""Golden regression test for extract_exam.py (project.md §5 / F8).

Runs the extractor against the two 114-year exam PDFs (which already have
100 human-verified questions in the repo's progress.json files) and checks:

  1. correct_answer must be 100/100 identical to the existing repo values.
  2. question_text must be > 95% similar (difflib ratio, tolerant of
     whitespace/punctuation normalization) for every question EXCEPT ones
     that involve an embedded image (code/table/chart screenshot) -- those
     are known to diverge because the existing repo's question_text for
     image questions contains a hand-authored description/transcription of
     the image (added by a prior human/AI pass) that a text-layer-only,
     OCR-free extractor cannot reproduce (see project.md rule 8 / red line
     2: never introduce OCR). An "image question" is one where EITHER the
     existing repo record or this extraction attached an `image` field.
  3. Exactly 50/50 questions per PDF, question numbers 1..50 contiguous.

Run directly:
    uv run --project tools python tools/tests/test_golden_answers.py
Or with pytest (also picked up if pytest is ever added to the project):
    uv run --project tools pytest tools/tests/test_golden_answers.py
"""
from __future__ import annotations

import difflib
import json
import sys
import tempfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

import extract_exam  # noqa: E402

SIMILARITY_THRESHOLD = 0.95

CASES = [
    {
        "label": "B1 (114 s1)",
        "pdf": REPO_ROOT / "source_pdfs" / "114年第二梯次中級AI應用規劃師第一科人工智慧技術應用與規劃(當次試題公告114_20251226000616.pdf",
        "subject": "s1",
        "exam_id": "114-2",
        "existing_json": REPO_ROOT / "subjects" / "1-ai" / "progress.json",
        "id_prefix": "exam-114-2-q",
        "pdf_dest_rel": "subjects/1-ai/past-exam.pdf",
    },
    {
        "label": "B3 (114 s3)",
        "pdf": REPO_ROOT / "source_pdfs" / "114年第二梯次中級AI應用規劃師第三科機器學習技術與應用(當次試題公告114_20251226000650.pdf",
        "subject": "s3",
        "exam_id": "114-2",
        "existing_json": REPO_ROOT / "subjects" / "3-ml" / "progress.json",
        "id_prefix": "exam-s3-114-2-q",
        "pdf_dest_rel": "subjects/3-ml/past-exam.pdf",
    },
]


def run_case(case: dict, image_dir: Path) -> dict:
    if not case["pdf"].exists():
        return {"skipped": True, "reason": f"source PDF not found: {case['pdf']}"}

    raw = extract_exam.stage1_parse(case["pdf"])
    questions = extract_exam.assemble(raw)
    warnings: list[str] = []
    result = extract_exam.emit(
        case["pdf"], questions, raw["images"], case["subject"], case["exam_id"],
        case["pdf_dest_rel"], image_dir, f"exam-{case['subject']}-{case['exam_id']}", warnings,
    )

    existing_all = json.loads(case["existing_json"].read_text(encoding="utf-8"))["verified_question_pool"]
    existing_by_num = {}
    for q in existing_all:
        if q["id"].startswith(case["id_prefix"]):
            try:
                existing_by_num[int(q["id"].split("q")[-1])] = q
            except ValueError:
                continue

    nums = sorted(int(q["id"].split("q")[-1]) for q in result)
    count_ok = len(result) == 50 and nums == list(range(1, 51))

    ans_total = 0
    ans_match = 0
    ans_mismatches = []
    text_rows = []
    for q in result:
        qn = int(q["id"].split("q")[-1])
        e = existing_by_num.get(qn)
        if e is None:
            text_rows.append((qn, None, "no existing record to compare"))
            continue
        ans_total += 1
        if q["correct_answer"] == e["correct_answer"]:
            ans_match += 1
        else:
            ans_mismatches.append((qn, q["correct_answer"], e["correct_answer"]))
        sim = difflib.SequenceMatcher(None, q["question_text"], e["question_text"]).ratio()
        is_image = bool(e.get("image")) or bool(q.get("image"))
        text_rows.append((qn, sim, is_image))

    non_image_low = [(qn, sim) for qn, sim, is_image in text_rows if sim is not None and not is_image and sim < SIMILARITY_THRESHOLD]
    image_rows = [(qn, sim) for qn, sim, is_image in text_rows if sim is not None and is_image]

    return {
        "skipped": False,
        "n_questions": len(result),
        "count_ok": count_ok,
        "nums": nums,
        "ans_total": ans_total,
        "ans_match": ans_match,
        "ans_mismatches": ans_mismatches,
        "non_image_low": non_image_low,
        "image_rows": sorted(image_rows),
        "warnings": warnings,
    }


def main():
    # Crops go to a throwaway temp dir, not into the repo -- this test only
    # checks text/answer fidelity, it isn't meant to produce committed image
    # assets (those come from the real `extract_exam.py` run in §G).
    with tempfile.TemporaryDirectory(prefix="ipas-quiz-golden-") as tmp:
        image_dir = Path(tmp)
        _main(image_dir)


def _main(image_dir: Path):
    overall_ok = True
    for case in CASES:
        print(f"=== {case['label']} ===")
        r = run_case(case, image_dir)
        if r["skipped"]:
            print(f"  SKIPPED: {r['reason']}")
            overall_ok = False
            continue

        print(f"  question count: {r['n_questions']}/50, contiguous 1..50: {r['count_ok']}")
        if not r["count_ok"]:
            overall_ok = False
            print(f"    nums={r['nums']}")

        print(f"  correct_answer match: {r['ans_match']}/{r['ans_total']}")
        if r["ans_mismatches"]:
            overall_ok = False
            print(f"    MISMATCHES: {r['ans_mismatches']}")

        print(f"  question_text similarity < {SIMILARITY_THRESHOLD:.0%} (non-image questions): {len(r['non_image_low'])}")
        if r["non_image_low"]:
            overall_ok = False
            for qn, sim in r["non_image_low"]:
                print(f"    FAIL q{qn}: sim={sim:.3f}")

        if r["image_rows"]:
            print(f"  (informational, not gating) image-question similarity, {len(r['image_rows'])} question(s):")
            for qn, sim in r["image_rows"]:
                print(f"    q{qn}: sim={sim:.3f}")

        if r["warnings"]:
            print(f"  {len(r['warnings'])} extractor warning(s):")
            for w in r["warnings"]:
                print(f"    - {w}")
        print()

    if overall_ok:
        print("GOLDEN TEST: PASS")
        sys.exit(0)
    else:
        print("GOLDEN TEST: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
