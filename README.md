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
- **Optional cross-device cloud sync** — point the app at your own Google Apps Script Web App URL and round history syncs bidirectionally through a Google Sheet you own (see "雲端同步設定" below); off by default, purely local otherwise
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

> Personal study notes (e.g. per-round score trackers) live under `notes/` locally, but `notes/` is gitignored so nothing personal lands in the public repo. Each visitor's quiz progress is kept in their own browser's `localStorage` by default — never sent anywhere unless the visitor opts into cloud sync (see below).

## Deploy to Vercel

This repo is structured for zero-config Vercel deployment.

```bash
gh repo create <name> --private --source=. --remote=origin --push
# then: vercel.com → New Project → Import → Deploy
```

Vercel auto-detects this as a static site. `index.html` is served at `/`. PDF deep-links use relative paths (`subjects/.../study-guide.pdf#page=N`) which work without modification.

## 雲端同步設定（跨裝置，選用）

預設情況下作答紀錄只存在單一瀏覽器的 `localStorage`。想在手機、電腦間同步歷史紀錄，
可以用自己的 Google 試算表當免費後端（Google Apps Script），完全不需要自己架 server：

1. 建一份新的 Google 試算表。
2. 上方選單「擴充功能」→「Apps Script」，把預設的 `Code.gs` 內容整個換成：

   ```js
   function doGet(e) {
     var sheet = SpreadsheetApp.getActiveSheet();
     var values = sheet.getDataRange().getValues();
     var rounds = [];
     for (var i = 1; i < values.length; i++) {
       var row = values[i];
       if (!row[0]) continue;
       rounds.push({
         id: row[0], subject_code: row[1], scope: row[2],
         shuffled: row[3] === true || row[3] === "TRUE",
         started: row[4], completed: row[5],
         responses: JSON.parse(row[6] || "[]")
       });
     }
     return ContentService.createTextOutput(JSON.stringify({ rounds: rounds }))
       .setMimeType(ContentService.MimeType.JSON);
   }

   function doPost(e) {
     var data = JSON.parse(e.postData.contents);
     var sheet = SpreadsheetApp.getActiveSheet();
     var lastRow = sheet.getLastRow();
     var ids = lastRow > 1 ? sheet.getRange(2, 1, lastRow - 1, 1).getValues().flat() : [];
     if (ids.indexOf(data.id) === -1) {
       sheet.appendRow([
         data.id, data.subject_code, data.scope, data.shuffled,
         data.started, data.completed, JSON.stringify(data.responses || [])
       ]);
     }
     return ContentService.createTextOutput(JSON.stringify({ result: "success" }))
       .setMimeType(ContentService.MimeType.JSON);
   }
   ```

3. 部署：右上角「部署」→「新增部署」→ 齒輪圖示選「網頁應用程式」。
   **執行身分**選「我」，**誰有存取權**選「所有人」，再點「部署」。
   跳出授權視窗時點「授予存取權」；若出現「未驗證」警告，點「進階」→「前往...(不安全)」→「允許」。
4. 複製部署完成後顯示的「網頁應用程式 URL」（`https://script.google.com/macros/s/.../exec`）。
5. 回到本 app，開「歷史紀錄」頁 → 「雲端同步」卡片，貼上網址並按「儲存並同步」。
6. 在其他裝置的瀏覽器貼上**同一組網址**，就會自動雙向同步（開頁時抓一次、每回合作答完寫回，用每回合的 `id` 去重，不會重複寫入）。

> 每次修改 Apps Script 程式碼後，要重新「管理部署」→「編輯」→ 選「新版本」→ 儲存，修改才會生效。
>
> 這是選用功能，不設定網址就完全維持原本的純本機、無後端行為。同步的內容只有分數統計
> （科目、主題、每題對錯與所選字母），**不含題目全文**——會存進你自己的 Google 試算表，
> 不會經過任何第三方伺服器。

## Disclaimer

The PDFs under `subjects/*/` and `shared/` are official materials published by the **經濟部產業發展署** (Industrial Development Administration, MOEA) for the iPAS certification program. They are included here for personal study reference. If you deploy this publicly, verify the iPAS materials' redistribution terms first — consider password-protecting the deployment, or replacing the embedded PDFs with links to the official iPAS download pages.

Question correctness for official past-exam/sample items is verified directly against the answer columns printed in the official PDFs. Explanations are written from the study guides. Any error is mine, not the official source's.

