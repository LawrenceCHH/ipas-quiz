#!/usr/bin/env python3
"""Extract an iPAS past-exam PDF (answer|question two-column table format)
into an exam-*.json draft (question_text/options/correct_answer/source/image
filled by the parser; topic/explanation left null for a later agent pass).

Three-stage, checkpointed design (see project.md §3.1):
    stage 1  parse    PDF -> raw_rows.json      (table rows + coordinates)
    stage 2  assemble raw_rows.json -> questions.json (cut into questions)
    stage 3  emit     questions.json -> exam-*.json  (schema + validation)

Each stage's output is deterministic and can be re-run independently by
pointing --raw-rows / --questions at an existing checkpoint file, so a bug
in stage 2/3 doesn't require re-running the (slow) PDF parse.

Usage:
    uv run --project tools python tools/extract_exam.py \\
        --pdf source_pdfs/....pdf --subject s1 --exam-id 115-1 \\
        --out subjects/1-ai/exam-115-1.json \\
        --pdf-dest subjects/1-ai/past-exam-115-1.pdf \\
        --image-dir shared/images
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import pdfplumber

REPO_ROOT = Path(__file__).resolve().parent.parent

# Watermark image bbox, identical on every page of the 115-year PDFs
# (confirmed by probing; 114-year PDFs have no images at all on text pages).
WATERMARK_BBOX = (102.5, 365.1, 492.8, 528.8)
WATERMARK_TOL = 0.5

MARKER_RE = re.compile(r"^\d+\.$")
# Usually options are one-per-line, but short options are sometimes packed
# onto a single physical PDF line (e.g. "(A)MAE;(B)MSE;(C)RMSE;(D)R2"), so
# option boundaries have to be found anywhere in the line, not just at
# position 0 (discovered via the golden-test run on 114 s3 q38/q39).
OPTION_ANY_RE = re.compile(r"\(([A-D])\)")
SHARED_STEM_RE = re.compile(r"回答第?\s*(\d+)\s*[~～\-至]\s*(\d+)\s*題")
CJK_RE = re.compile(r"[一-鿿]")
Y_LINE_TOL = 3  # points; words within this top-distance are treated as one visual line

# pdfminer/pdfplumber occasionally mis-orders a full-width opening
# quote/bracket glyph that immediately follows an option letter, because
# its glyph bounding box starts to the left of where it's actually drawn
# (a font-metrics quirk of certain CJK punctuation), e.g. the PDF's raw
# text layer literally reads "(A「)" instead of "(A)「". All characters are
# present, just locally transposed -- this restores the correct order
# rather than dropping/inventing anything. Found via 115-1 s1 Q28.
BRACKET_GLYPH_SWAP_RE = re.compile(r"([A-D])([「『])\)")


# ---------------------------------------------------------------------------
# Stage 1: parse
# ---------------------------------------------------------------------------

def is_watermark(bbox) -> bool:
    return all(abs(a - b) < WATERMARK_TOL for a, b in zip(bbox, WATERMARK_BBOX))


def group_lines(words):
    """Group a list of pdfplumber word-dicts into visual lines (clustered by
    `top`, tolerant of small offsets), each line's words joined left-to-right
    by a single space. Returns list of line strings.

    Uses sequential clustering (sort by top, start a new cluster whenever the
    gap from the cluster's first word exceeds Y_LINE_TOL) rather than fixed
    modular buckets (`round(top/TOL)`) -- the latter has a hard boundary
    that can split two words as little as 0.1pt apart into different lines
    if they straddle a bucket edge (e.g. 379.5 and 379.7 rounding to
    different buckets at TOL=3), scrambling word order. Found via 115-1 s3
    Q40's option block, where "(A)" and its answer text sit ~0.2pt apart."""
    if not words:
        return []
    ws = sorted(words, key=lambda w: w["top"])
    clusters = [[ws[0]]]
    cluster_top = ws[0]["top"]
    for w in ws[1:]:
        if w["top"] - cluster_top <= Y_LINE_TOL:
            clusters[-1].append(w)
        else:
            clusters.append([w])
            cluster_top = w["top"]
    lines = []
    for group in clusters:
        group_sorted = sorted(group, key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in group_sorted)
        text = BRACKET_GLYPH_SWAP_RE.sub(r"\1)\2", text)
        lines.append(text)
    return lines


def parse_row(page, row, page_no: int, row_idx: int) -> dict:
    boundary = row.cells[0][2]
    crop = page.crop(row.bbox)
    words = crop.extract_words(use_text_flow=False, keep_blank_chars=False)

    ans_words = [w for w in words if w["x0"] < boundary]
    q_words_all = [w for w in words if w["x0"] >= boundary]

    markers = []
    q_words = []
    for w in q_words_all:
        norm = unicodedata.normalize("NFKC", w["text"])
        if MARKER_RE.match(norm):
            markers.append(norm)
        else:
            q_words.append(w)

    ans_letters = "".join(
        ch for w in ans_words for ch in unicodedata.normalize("NFKC", w["text"]) if ch.isalpha()
    )

    q_lines = group_lines(q_words)

    return {
        "page": page_no,
        "row": row_idx,
        "bbox": list(row.bbox),
        "boundary": boundary,
        "ans_letters": ans_letters,
        "markers": markers,
        "q_lines": q_lines,
    }


def stage1_parse(pdf_path: Path) -> dict:
    pdf = pdfplumber.open(str(pdf_path))
    raw_rows = []
    images = []
    for page_no, page in enumerate(pdf.pages, start=1):
        tables = page.find_tables()
        if not tables:
            continue
        table = tables[0]
        for row_idx, row in enumerate(table.rows):
            if row_idx == 0:
                continue  # header row (label text is unreliable on p.11+, always skip by position)
            raw_rows.append(parse_row(page, row, page_no, row_idx))
        for im in page.images:
            bbox = (im["x0"], im["top"], im["x1"], im["bottom"])
            if is_watermark(bbox):
                continue
            images.append({"page": page_no, "bbox": list(bbox), "srcsize": im.get("srcsize")})
    pdf.close()
    return {"pdf": str(pdf_path), "rows": raw_rows, "images": images}


# ---------------------------------------------------------------------------
# Stage 2: assemble
# ---------------------------------------------------------------------------

def strip_shared_stem_lines(lines: list[str]):
    """Detect + remove '回答第 X~Y 題' navigational sentences from a row's
    lines, returning (kept_lines, shared_hits [(start,end), ...]).

    Searches the row's lines *concatenated*, not line-by-line: pdfplumber
    sometimes wraps the sentence across a line break (e.g. "...請回答" on one
    line, "第 42~43 題。" on the next, 115-1 s3 Q41), so a per-line regex
    search misses it and the trailing declaration bleeds into whatever
    question was still open. Any line that overlaps the match span is
    dropped in full (these declaration sentences are self-contained; they
    don't share a line with other content worth keeping in the cases seen)."""
    if not lines:
        return lines, []
    norm_lines = [unicodedata.normalize("NFKC", ln) for ln in lines]
    spans = []  # (start, end) offsets into the concatenated string, per line
    offset = 0
    for nl in norm_lines:
        spans.append((offset, offset + len(nl)))
        offset += len(nl)
    joined = "".join(norm_lines)
    hits = []
    drop_idx = set()
    for m in SHARED_STEM_RE.finditer(joined):
        hits.append((int(m.group(1)), int(m.group(2))))
        for i, (s, e) in enumerate(spans):
            if s < m.end() and e > m.start():  # overlaps the match
                drop_idx.add(i)
    kept = [ln for i, ln in enumerate(lines) if i not in drop_idx]
    return kept, hits


def assemble(raw: dict) -> list[dict]:
    """Cut raw_rows into a list of raw question dicts:
    {qnum, ans_letter, lines: [str], rows: [{page,row,bbox}], shared_groups: [(a,b)]}

    A "回答第 X~Y 題" line inside a *continuation* row (no answer letter, no
    question-number marker on that row) marks a shared-scenario block for
    the next question group (e.g. a VGG16 model-summary block before Q42 of
    114 s3, or a Titanic dataset intro before Q48-50). That block is
    unrelated to whatever question was previously open, so it must NOT be
    appended to it -- instead the whole row is moved into a `pending`
    buffer that gets prepended to the next row that actually opens a new
    question (ans letter + marker present). Discovered via the golden test
    (114 s3 q41/q45/q47 were absorbing the next group's scenario text)."""
    questions = []
    current = None
    pending = None  # list of lines waiting to be prepended to the next new question

    def close_current():
        if current is not None:
            questions.append(current)

    for r in raw["rows"]:
        has_new_q = bool(r["ans_letters"]) and bool(r["markers"])
        lines = list(r["q_lines"])

        # Detect + strip "回答第 X~Y 題" navigational lines (never part of the
        # stem text; matches observed precedent in the existing 114 data
        # where this sentence is dropped from both endpoints, not copied).
        lines, shared_hits = strip_shared_stem_lines(lines)
        row_is_shared_decl = bool(shared_hits)

        if has_new_q:
            close_current()
            qnum = int(unicodedata.normalize("NFKC", r["markers"][0]).rstrip("."))
            init_lines = list(pending["lines"]) if pending else []
            init_rows = list(pending["rows"]) if pending else []
            init_shared = list(pending["shared_groups"]) if pending else []
            pending = None
            current = {
                "qnum": qnum,
                "ans_letter": unicodedata.normalize("NFKC", r["ans_letters"]),
                "lines": init_lines + lines,
                "rows": init_rows + [{"page": r["page"], "row": r["row"], "bbox": r["bbox"], "boundary": r["boundary"], "is_pending": False}],
                "shared_groups": init_shared + shared_hits,
            }
        elif row_is_shared_decl:
            # New shared-scenario block: close whatever was open (it's
            # unrelated), start (or continue) the pending buffer instead.
            close_current()
            current = None
            if pending is None:
                pending = {"lines": [], "rows": [], "shared_groups": []}
            pending["lines"].extend(lines)
            pending["rows"].append({"page": r["page"], "row": r["row"], "bbox": r["bbox"], "boundary": r["boundary"], "is_pending": True})
            pending["shared_groups"].extend(shared_hits)
        else:
            # continuation row (no answer letter, no marker, no shared-decl)
            if current is not None:
                current["lines"].extend(lines)
                current["rows"].append({"page": r["page"], "row": r["row"], "bbox": r["bbox"], "boundary": r["boundary"], "is_pending": False})
            elif pending is not None:
                pending["lines"].extend(lines)
                pending["rows"].append({"page": r["page"], "row": r["row"], "bbox": r["bbox"], "boundary": r["boundary"], "is_pending": True})
            else:
                # Nothing open yet and nothing to attach this to. Surface it
                # rather than silently dropping content.
                current = {
                    "qnum": None,
                    "ans_letter": "",
                    "lines": lines,
                    "rows": [{"page": r["page"], "row": r["row"], "bbox": r["bbox"], "boundary": r["boundary"], "is_pending": False}],
                    "shared_groups": [],
                }
    close_current()
    if pending and (pending["lines"] or pending["rows"]):
        questions.append({"qnum": None, "ans_letter": "", "lines": pending["lines"], "rows": pending["rows"], "shared_groups": pending["shared_groups"]})
    return questions


# ---------------------------------------------------------------------------
# Stage 3: emit (text reconstruction, option split, schema, images)
# ---------------------------------------------------------------------------

def smart_join(lines: list[str]) -> str:
    out = ""
    for ln in lines:
        if not ln:
            continue
        if not out:
            out = ln
            continue
        last, first = out[-1], ln[0]
        if last.isascii() and last.isalnum() and first.isascii() and first.isalnum():
            out += " " + ln
        else:
            out += ln
    return out


FULLWIDTH_OPEN_RE = re.compile(r"([「『（【])\s+")
FULLWIDTH_CLOSE_RE = re.compile(r"\s+([，。；：？！」』）】、])")


def pangu(text: str) -> str:
    text = re.sub(r"([一-鿿])([A-Za-z0-9])", r"\1 \2", text)
    text = re.sub(r"([A-Za-z0-9])([一-鿿])", r"\1 \2", text)
    text = re.sub(r"[ \t]+", " ", text)
    # Chinese typesetting doesn't put a space next to full-width
    # punctuation; this only removes stray spaces adjacent to it (e.g. a
    # leftover join-space after the BRACKET_GLYPH_SWAP_RE reorder fix), it
    # never touches the CJK<->Latin spacing added just above.
    text = FULLWIDTH_OPEN_RE.sub(r"\1", text)
    text = FULLWIDTH_CLOSE_RE.sub(r"\1", text)
    return text.strip()


def clean_text(lines: list[str]) -> str:
    joined = smart_join(lines)
    joined = unicodedata.normalize("NFKC", joined)
    joined = pangu(joined)
    return joined.strip()


def split_stem_options(lines: list[str]):
    """Split a question's raw lines into (stem_lines, {A:[lines],...}).
    Options are normally one-per-line (§3.5's "行首" rule), but short
    options can be packed onto one physical line (e.g.
    "(A)MAE;(B)MSE;(C)RMSE;(D)R2"), so once inside the option block this
    scans for `(X)` markers anywhere in the line, not just at position 0.

    The *first* stem->option transition, however, is only accepted at
    position 0 of a line. Some fill-in-the-blank questions reference blanks
    named "(A)"/"(B)" mid-sentence in the stem itself (e.g. "...下圖中的程式
    碼中(A)與(B)的函數應填入何者？", 115-1 s3 Q40) before the real options
    start on their own line -- requiring position 0 for the *first* match
    only (matches can be mid-line for subsequent ones, once we're
    confidently inside the option block) avoids misfiring on those refs
    while still handling the packed-options case.

    Must run on RAW (pre-join) lines so option text doesn't get merged
    across visual lines first."""
    stem_lines = []
    opt_lines = {"A": [], "B": [], "C": [], "D": []}
    cur = None
    for ln in lines:
        matches = list(OPTION_ANY_RE.finditer(ln))
        if cur is None and matches and matches[0].start() != 0:
            matches = []  # not yet in option mode: only a true line-start match may open it
        if not matches:
            (opt_lines[cur] if cur is not None else stem_lines).append(ln)
            continue
        pre = ln[:matches[0].start()]
        if pre:
            (opt_lines[cur] if cur is not None else stem_lines).append(pre)
        for i, m in enumerate(matches):
            cur = m.group(1)
            seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(ln)
            seg = ln[m.end():seg_end]
            if seg:
                opt_lines[cur].append(seg)
    return stem_lines, opt_lines


def strip_trailing_sep(text: str) -> str:
    return re.sub(r"[；;]\s*$", "", text).strip()


def image_for_question(q: dict, raw_images: list[dict], image_dir: Path, qid: str):
    """Find images whose bbox falls in one of this question's row y-ranges
    (same page), crop = row bbox ∩ question-column x-range (per §3.6),
    save to image_dir. Returns (saved, extra) where `saved` is
    (page_no, crop_bbox, repo_rel_path, out_path) for the primary crop, and
    `extra` is a list of the same tuple for any additional image-bearing
    rows (saved to disk but not attached to the question's single `image`
    field).

    Row preference for the primary crop: the question's OWN rows (its
    opening row + its own continuation rows) are checked before rows that
    were only prepended from a shared "回答第 X~Y 題" scenario block. A
    scenario block's image is usually generic setup/context, while
    "(下圖)"/"參考下圖" in the question's own text is almost always
    pointing at a figure on the question's own row -- picking the pending
    block's image as primary got this backwards for 115-1 s3 Q44/Q46 (the
    actual referenced code+options image ended up as an unused "-extra1"
    file instead of the attached `image`)."""
    own_rows = [rm for rm in q["rows"] if not rm.get("is_pending")]
    pending_rows = [rm for rm in q["rows"] if rm.get("is_pending")]

    saved = None
    extra = []
    for rowmeta in own_rows + pending_rows:
        page_no = rowmeta["page"]
        row_bbox = rowmeta["bbox"]
        boundary = rowmeta["boundary"]
        row_top, row_bottom = row_bbox[1], row_bbox[3]
        row_right = row_bbox[2]
        hits = [
            im for im in raw_images
            if im["page"] == page_no and row_top <= im["bbox"][1] < row_bottom
        ]
        if not hits:
            continue
        crop_bbox = (boundary, row_top, row_right, row_bottom)
        fname = f"{qid}-p{page_no}.png"
        out_path = image_dir / fname
        rel_path = f"shared/images/{fname}"
        if saved is None:
            saved = (page_no, crop_bbox, rel_path, out_path)
        else:
            extra.append((page_no, crop_bbox, rel_path, out_path))
    return saved, extra


def emit(pdf_path: Path, questions: list[dict], raw_images: list[dict],
         subject_code: str, exam_id: str, out_pdf_rel: str, image_dir: Path,
         id_prefix: str, warnings: list[str]) -> list[dict]:
    result = []
    open_pdf = pdfplumber.open(str(pdf_path))
    try:
        for q in questions:
            if q["qnum"] is None:
                warnings.append(f"orphan continuation content before any question opened (rows={q['rows']}); dropped")
                continue
            stem_lines, opt_lines = split_stem_options(q["lines"])
            stem = clean_text(stem_lines)
            options = {}
            for letter in "ABCD":
                raw_opt = clean_text(opt_lines[letter])
                raw_opt = strip_trailing_sep(raw_opt)
                options[letter] = raw_opt
            missing_opts = [L for L in "ABCD" if not options[L]]
            if missing_opts:
                warnings.append(f"q{q['qnum']}: options missing/empty for {missing_opts}")

            first_row = q["rows"][0]
            src_page = first_row["page"]

            qid = f"{id_prefix}-q{q['qnum']}"
            saved, extra = image_for_question(q, raw_images, image_dir, qid)

            image_rel = None
            if saved:
                page_no, crop_bbox, rel_path, out_path = saved
                pg = open_pdf.pages[page_no - 1]
                im = pg.crop(crop_bbox).to_image(resolution=200)
                image_dir.mkdir(parents=True, exist_ok=True)
                im.save(str(out_path))
                image_rel = rel_path
                if extra:
                    for i, (pn, cb, rp, op) in enumerate(extra):
                        rp2 = rp.replace(".png", f"-extra{i+1}.png")
                        op2 = Path(str(op).replace(".png", f"-extra{i+1}.png"))
                        pg2 = open_pdf.pages[pn - 1]
                        im2 = pg2.crop(cb).to_image(resolution=200)
                        im2.save(str(op2))
                    warnings.append(
                        f"q{q['qnum']}: {len(extra)} additional image-bearing row(s) beyond the primary "
                        f"crop were also saved (suffix -extraN.png) but NOT attached to `image` -- "
                        f"needs manual review (§G7)."
                    )
            if q["shared_groups"]:
                warnings.append(f"q{q['qnum']}: shared-stem marker seen for range(s) {sorted(set(q['shared_groups']))} (navigational sentence stripped, not duplicated -- matches existing 114 precedent)")

            question = {
                "id": qid,
                "topic": None,
                "question_text": stem,
                "options": options,
                "correct_answer": q["ans_letter"],
                "source": {
                    "file": out_pdf_rel,
                    "page": src_page,
                    "evidence": f"answer column shows '{q['ans_letter']}' for question {q['qnum']}",
                },
                "verified": False,
                "verification_needed": "topic,explanation",
                "explanation": None,
                "subject_code": subject_code,
            }
            if image_rel:
                question["image"] = image_rel
            result.append(question)
    finally:
        open_pdf.close()
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--subject", required=True, choices=["s1", "s2", "s3", "e1", "e2"])
    ap.add_argument("--exam-id", required=True, help="e.g. 115-1")
    ap.add_argument("--out", required=True, help="output exam-*.json path")
    ap.add_argument("--pdf-dest", required=True, help="where to copy the PDF inside the repo (ASCII filename)")
    ap.add_argument("--image-dir", default="shared/images")
    ap.add_argument("--raw-rows", help="checkpoint path for stage-1 output (default: alongside --out)")
    ap.add_argument("--questions", help="checkpoint path for stage-2 output (default: alongside --out)")
    ap.add_argument("--skip-copy", action="store_true", help="don't copy the PDF (assume already at --pdf-dest)")
    ap.add_argument("--from-stage", choices=["parse", "assemble", "emit"], default="parse")
    args = ap.parse_args()

    pdf_src = Path(args.pdf)
    out_path = Path(args.out)
    pdf_dest = Path(args.pdf_dest)
    image_dir = Path(args.image_dir)
    if not image_dir.is_absolute():
        image_dir = REPO_ROOT / image_dir

    # Checkpoints default to a `.checkpoints/` subdirectory next to --out,
    # not a `*.json` sibling of it -- build_pool.py globs `subjects/*/*.json`
    # (one level deep) for real question-pool files, and a raw_rows/questions
    # checkpoint sitting directly in subjects/<x>/ would match that glob and
    # crash it (it's a bare list, not a {"verified_question_pool": [...]}
    # doc). A one-level-deeper subdirectory is invisible to that glob.
    checkpoint_dir = out_path.parent / ".checkpoints"
    raw_rows_path = Path(args.raw_rows) if args.raw_rows else checkpoint_dir / (out_path.stem + ".raw_rows.json")
    questions_path = Path(args.questions) if args.questions else checkpoint_dir / (out_path.stem + ".questions.json")
    if not args.raw_rows or not args.questions:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

    id_prefix = f"exam-{args.subject}-{args.exam_id}"

    if not args.skip_copy:
        pdf_dest_abs = pdf_dest if pdf_dest.is_absolute() else REPO_ROOT / pdf_dest
        pdf_dest_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(pdf_src, pdf_dest_abs)
        print(f"copied {pdf_src} -> {pdf_dest_abs}")

    pdf_for_parsing = pdf_dest if pdf_dest.is_absolute() else REPO_ROOT / pdf_dest
    if not pdf_for_parsing.exists():
        pdf_for_parsing = pdf_src  # allow parsing directly from source_pdfs without copy

    if args.from_stage == "parse":
        raw = stage1_parse(pdf_for_parsing)
        raw_rows_path.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"stage1: {len(raw['rows'])} rows, {len(raw['images'])} non-watermark images -> {raw_rows_path}")
    else:
        raw = json.loads(raw_rows_path.read_text(encoding="utf-8"))

    if args.from_stage in ("parse", "assemble"):
        questions = assemble(raw)
        questions_path.write_text(json.dumps(questions, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"stage2: {len(questions)} questions -> {questions_path}")
    else:
        questions = json.loads(questions_path.read_text(encoding="utf-8"))

    warnings: list[str] = []
    out_pdf_rel = pdf_dest.as_posix() if not pdf_dest.is_absolute() else str(pdf_dest.relative_to(REPO_ROOT))
    result = emit(pdf_for_parsing, questions, raw["images"], args.subject, args.exam_id,
                  out_pdf_rel, image_dir, id_prefix, warnings)

    out_doc = {
        "version": 1,
        "test_name": f"iPAS AI 應用規劃師中級 {args.subject} 考題（{args.exam_id}）",
        "subject_code": args.subject,
        "source_files": [out_pdf_rel],
        "verified_question_pool": result,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"stage3: {len(result)} questions emitted -> {out_path}")
    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  - {w}")

    nums = [q["qnum"] for q in questions if q["qnum"] is not None]
    expected = list(range(1, len(nums) + 1)) if nums else []
    if sorted(nums) != expected:
        print(f"\n!! question numbers not contiguous 1..N: got {sorted(nums)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
