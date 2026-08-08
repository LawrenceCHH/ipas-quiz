# iPAS AI 應用規劃師 練習

A self-contained static webapp for practicing the **iPAS AI 應用規劃師** exam across 初級 and 中級 subjects:

- **中級科目一** · 人工智慧技術應用與規劃 (AI Technology Application & Planning)
- **中級科目二** · 大數據處理分析與應用 (Big Data Processing, Analysis & Applications)
- **中級科目三** · 機器學習技術與應用 (Machine Learning Technology & Applications)
- **初級科目一** · 人工智慧基礎概論 (AI Foundations)
- **初級科目二** · 生成式 AI 應用與規劃 (Generative AI Applications & Planning)

895 MCQ questions: 595 中級 questions (past exam + sample + study-guide generated practice) and 300 初級 questions (50 verified past-exam + 100 study-guide generated practice per entry-level subject), with Markdown explanations, source citations, and topic categorization.

## Run locally

```bash
open index.html   # macOS
# or just double-click index.html in Finder/Explorer
```

No build step, no server required. State persists in `localStorage`.

## Features

- **Subject + topic filters** — drill into a specific subject or topic block
- **Configurable rounds** — 5/10/15/20/all questions per session
- **Instant feedback** — correct/wrong + correct answer + source page
- **"💡 為什麼？" panel** — pre-generated explanation per question (why correct, why each wrong option, memory hook) + deep-link to study guide PDF at the right page
- **Option shuffle mode** — randomize A/B/C/D order to prevent position-memorization; explanation auto-rewrites to match displayed order
- **Round history + cumulative weak-topic tracking** — scoped per subject
- **Keyboard shortcuts** — `A`/`B`/`C`/`D` (with `Cmd+C` etc. preserved), `Enter` to advance, `W` to toggle the why panel

## Project structure

```
.
├── index.html                  # The app — single self-contained HTML
├── README.md
├── tools/                      # Dev-only build/extraction scripts (see "Updating the question pool" below)
│   ├── build_pool.py           # subjects/**/*.json → index.html's POOL literal
│   ├── extract_exam.py         # official exam PDF → exam-*.json
│   ├── hooks/pre-commit        # versioned copy of the git pre-commit hook
│   └── tests/test_golden_answers.py
├── subjects/
│   ├── 1-ai/                  # 中級科目一
│   │   ├── past-exam.pdf       # 114年第二梯次 official past exam
│   │   ├── past-exam-115-1.pdf # 115年第一次 official past exam
│   │   ├── study-guide.pdf     # 學習指引
│   │   ├── progress.json       # Question pool
│   │   └── exam-115-1.json     # 115年第一次 questions
│   ├── 2-bigdata/              # 中級科目二
│   │   ├── past-exam.pdf
│   │   ├── study-guide.pdf
│   │   └── progress.json
│   ├── 3-ml/                   # 中級科目三
│   │   ├── past-exam.pdf
│   │   ├── past-exam-115-1.pdf # 115年第一次 official past exam
│   │   ├── study-guide.pdf
│   │   ├── progress.json
│   │   └── exam-115-1.json     # 115年第一次 questions
│   ├── entry-1-ai/             # 初級科目一
│   │   ├── past-exam.pdf       # 115年第二次 official past exam
│   │   ├── study-guide.pdf
│   │   └── progress.json       # 50 past-exam + 100 study-guide generated
│   └── entry-2-genai/          # 初級科目二
│       ├── past-exam.pdf       # 115年第二次 official past exam
│       ├── study-guide.pdf
│       └── progress.json       # 50 past-exam + 100 study-guide generated
└── shared/
    ├── sample-questions.pdf    # 114年9月版 樣題 (covers all 3 subjects)
    └── images/                 # Reference figures used by image-based questions
```

## Updating the question pool

`index.html` has no `fetch()` — the question pool is a JS literal (`const POOL =
[...]`, around line 378, roughly 660k characters on one line) baked directly into the
file. **`subjects/**/*.json` is the source of truth; the `POOL` literal in
`index.html` is a generated artifact rebuilt from it.**

The only correct workflow for changing questions:

```bash
# 1. edit subjects/<subject>/*.json
# 2. rebuild index.html's POOL from the JSON
uv run --project tools python tools/build_pool.py
# 3. commit both the JSON and the regenerated index.html
```

**Never hand-edit the `POOL` array inside `index.html`.** Skipping the rebuild step
is exactly what happened in commit `0b952e7`: an option-length fix landed only in
`progress.json`, `index.html` was never regenerated, and everyone using the app kept
practicing the pre-fix questions for three months before anyone noticed.

`tools/build_pool.py --check` recomputes the pool without writing and exits 1 if
`index.html` is out of sync with the JSON. That check is also wired up as a git
`pre-commit` hook so a drifted commit gets blocked automatically instead of relying
on someone remembering to run it. Git hooks under `.git/hooks/` aren't tracked by
git, so a versioned copy lives at `tools/hooks/pre-commit` — reinstall it after every
fresh clone:

```bash
ln -sf ../../tools/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Other scripts under `tools/`:

- `tools/extract_exam.py` — extracts a newly published official past-exam PDF into
  an `exam-*.json` file. It reads the PDF's text layer directly (question text,
  options, and the answer column) — no OCR is used anywhere in this pipeline.
  `explanation`/`topic` still need to be filled in by hand afterward and the
  question flipped to `verified: true` before `build_pool.py` will pick it up.
- `tools/tests/test_golden_answers.py` — regression test that re-extracts the two
  114年 past exams and checks the results against the 100 questions in this repo
  whose answers were already verified by hand.

Everything under `tools/` runs via `uv run --project tools python tools/...` — it's
a dev-only toolchain for maintainers, not something needed to just run the quiz app.

> Personal study notes (e.g. per-round score trackers) live under `notes/` locally, but `notes/` is gitignored so nothing personal lands in the public repo. Each visitor's quiz progress is kept in their own browser's `localStorage` — never sent anywhere.

## Deploy to Vercel

This repo is structured for zero-config Vercel deployment.

```bash
gh repo create <name> --private --source=. --remote=origin --push
# then: vercel.com → New Project → Import → Deploy
```

Vercel auto-detects this as a static site. `index.html` is served at `/`. PDF deep-links use relative paths (`subjects/.../study-guide.pdf#page=N`) which work without modification.

## Disclaimer

The PDFs under `subjects/*/` and `shared/` are official materials published by the **經濟部產業發展署** (Industrial Development Administration, MOEA) for the iPAS certification program. They are included here for personal study reference. If you deploy this publicly, verify the iPAS materials' redistribution terms first — consider password-protecting the deployment, or replacing the embedded PDFs with links to the official iPAS download pages.

Question correctness for official past-exam/sample items is verified directly against the answer columns printed in the official PDFs. Explanations are written from the study guides. Any error is mine, not the official source's.

