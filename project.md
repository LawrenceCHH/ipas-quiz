# 專案說明（常駐參考 — 後續 agent 動手前先讀這一節）

## 這是什麼

iPAS AI 應用規劃師的考古題練習 app。**一個自給自足的靜態 `index.html`**，
使用者雙擊就能開（`file://`），不需要 server、不需要 build、不連任何後端。
作答記錄存在瀏覽器 `localStorage`，不上傳。另有部署到 Vercel。

## 架構（三句話講完）

```
subjects/*/*.json          ← 題庫的「唯一真相」(system of record)
        ↓  tools/build_pool.py 合併、驗證、重建
index.html 第 378 行  const POOL = [...]   ← app 實際讀的內嵌陣列
        ↓
localStorage               ← 只存作答記錄，與題庫無關
```

`index.html` **沒有任何 `fetch()`**。第 378 行是單獨一整行、約 66 萬字元的 JS
常數字面量（`const POOL = [` 開頭、`];` 結尾），是全檔唯一的資料區；其餘
1311 行都是樣式與邏輯，改題庫時完全不該碰。

**改題庫的唯一正確流程**：改 `subjects/*/*.json`，然後跑
`uv run --project tools python tools/build_pool.py`。絕不手改 `index.html`
——`0b952e7` 就是漏了這步，造成 298 題 drift 三個月沒被發現（細節見 `git log`）。
`.git/hooks/pre-commit` 會在 commit 前自動擋下沒同步的情況（安裝指令見 README）。

## 檔案地圖

| 路徑 | 說明 |
|---|---|
| `index.html` | app 本體。資料在 `:378`，其餘是程式 |
| `index.html:382` `SUBJECTS` | 五個科目的中繼資料（`s1 s2 s3 e1 e2`） |
| `index.html:537` `pdfHref()` | 把 `source.file` 組成 `#page=N` deep link |
| `index.html:565` `poolForSubject()` | 純靠 `q.subject_code` 過濾科目 |
| `index.html:658` `translateExplanation()` | 選項打亂時重寫解析裡的 A/B/C/D |
| `subjects/<科目>/progress.json` | 既有題庫 |
| `subjects/{1-ai,3-ml}/exam-115-1.json` | 115 年第一次考題（各 50 題） |
| `subjects/<科目>/past-exam*.pdf` | 官方歷屆試題，`source.file` 指向它 |
| `subjects/<科目>/study-guide.pdf` | 學習指引，寫 `explanation` 的依據 |
| `shared/sample-questions.pdf` | 官方樣題（涵蓋中級三科，114年9月版；已確認無 115 年新版） |
| `shared/images/` | 圖表題的裁切圖 |
| `source_pdfs/` | 原始 PDF 暫存區（**untracked**，不進 git） |
| `tools/build_pool.py` | JSON → `index.html:378` 重建 POOL。`--check` 驗同步 |
| `tools/extract_exam.py` | 官方 PDF → `exam-*.json`（三階段，checkpoint 可重跑，用座標而非文字掃描切欄） |
| `tools/tests/test_golden_answers.py` | 對 114 年兩科 100 題的回歸測試 |
| `tools/hooks/pre-commit` | `--check` 的 pre-commit hook 版控副本 |

## 不變的規則（動手前必讀）

1. **官方題逐字保留**。`exam-*` / `sample-*` / `entry-*` 的 `question_text`、
   `options`、`correct_answer` 一律照抄官方 PDF，**永遠不要改寫、不要做選項長度
   平衡**。官方題「正解偏長」（命中率 49%）是真實考題的性質，修掉等於偽造素材。
   選項平衡只對 `generated: true` 的 AI 生成題有意義。
2. **答案來自官方答案欄，不是推理出來的**。agent 只負責解釋「為什麼是這個答案」。
   若認為官方答案有誤，記進 `verification_needed` 提報，**不要自行改
   `correct_answer`**。
3. **`explanation` 的三段式格式是硬約束，不是慣例**。`translateExplanation()`
   會用 regex 在選項打亂時重寫字母，格式寫錯就會對不上選項：
   - 標題 `**為什麼 X 是正解:**`（字母前後要有半形空白）← **真正的硬約束**
   - 必須有「記憶要點」段
   - 錯誤選項條列寫 `- A. …` 單字母（`- A/B. …` 合併寫法其實已被 regex 支援，
     但仍建議新題維持單字母，`build_pool.py` 只會給 Warning 不會擋）
4. **`topic` 要沿用既有詞彙**（清單見下方〈topic 詞彙表〉），不要自由發明，
   否則科目篩選的 topic 清單會碎片化。真的沒有適合的才新增，且要在 commit
   message 裡明確列出新增了什麼、為什麼。
5. **`id` 必須跨全部 json 唯一**，不能只檢查同一個檔案內。
6. **`subject_code` 每題都要填**。`poolForSubject()` 純靠這欄過濾，缺了在「依科目
   篩選」時題目會消失。`build_pool.py` 用目錄名（`1-ai→s1` 等）自動補值，
   但只在記憶體裡做、不寫回 JSON，所以獨立比對 JSON vs POOL 時這欄「不一致」
   是設計使然，不是 bug——請用 `build_pool.py --check` 驗證真正的同步狀態。
7. **`source.file` 必須是 ASCII 相對路徑**（會被拿去組 URL）。PDF 進 repo 前要
   改成 `past-exam-115-1.pdf` 這種乾淨檔名，不要留中文長檔名。
8. **絕不引入 OCR**。這批 PDF 的文字層是乾淨的，一律直讀。實測過 OCR-based 抽取
   在繁體中文上會靜默改字（錯字率 20.7% vs 直讀 0.6%）且慢 12 倍。
9. **改完 json 一定要重建 POOL**（見上方「改題庫的唯一正確流程」）。
10. **圖表題的圖要裁掉答案欄**再存進 `shared/images/`，不要放整頁截圖。
11. **不要動 `localStorage` 的 schema**（`test-prep-rounds-v1`），會清掉使用者的
    歷史作答記錄。
12. **抽取新考題時切欄一律用座標，不要讀表頭文字**（`row.cells[0][2]` 取第一格
    右緣當欄界）。115 年科三 PDF 從某頁起表頭文字本身印反（`題目 答案`），是
    原始 PDF 的 bug，欄位座標沒變，只有標籤印反。

## 目前的維護範圍

| 科目 | 代碼 | 狀態 |
|---|---|---|
| 中級科目一 · AI 技術應用與規劃 | `s1` | ✅ **主要維護對象** |
| 中級科目三 · 機器學習技術與應用 | `s3` | ✅ **主要維護對象** |
| 中級科目二 · 大數據處理分析與應用 | `s2` | ⏸ 不在考試範圍，既有 165 題留著不動，不再新增 |
| 初級科目一 / 科目二 | `e1` `e2` | ⏸ 使用者不會用到，既有 300 題留著不動，已知品質問題不修 |

「留著不動」= 題目繼續留在 POOL 裡給別的使用者用，但不投入維護、統計時要分開列。

## 快速自我檢查

跑 `uv run --project tools python tools/build_pool.py --check`（同步就 exit 0，
`git commit` 前也會自動跑一次）。

**現況（2026-08-08）**：POOL 895 題 / JSON 895 題，除設計使然的 `subject_code`
（見規則 6）外，其餘欄位 0 題不一致。分科：`s1` 215、`s2` 165、`s3` 215、
`e1` 150、`e2` 150。

## topic 詞彙表（新增考題時必查）

- **s1（47 種）**：`AI/Adoption` `AI/Definition` `AI/Planning` `AI/Risk`
  `CV/Classification` `CV/Detection` `CV/OCR` `CV/Pose` `CV/Segmentation` `CV/ViT`
  `Data/Augmentation` `Data/Drift` `Data/Preprocessing` `Deploy/Integration`
  `Deploy/Kubernetes` `Deploy/MLOps` `GenAI/Compression` `GenAI/Diffusion`
  `GenAI/FineTuning` `GenAI/GAN` `GenAI/PromptEngineering` `GenAI/RAG`
  `ML/Classification` `ML/Clustering` `ML/Evaluation` `ML/Overfitting` `ML/Regression`
  `Multimodal/CLIP` `Multimodal/Fusion` `Multimodal/General`
  `NLP/BERT-vs-GPT` `NLP/Embedding` `NLP/General` `NLP/Hallucination` `NLP/LLM-Eval`
  `NLP/NER` `NLP/RAG` `NLP/Sentiment` `NLP/Summarization` `NLP/Tokenization`
  `NLP/Transformer` `NLP/Translation` `Risk/Compliance` `Risk/Copyright`
  `Risk/Privacy` `Risk/Security`
  （注意舊資料裡還有一個沒斜線的 `Multimodal`，新題一律用 `Multimodal/General`）
- **s3（35 種）**：`Bias/Fairness` `BigData/Processing` `DL/Basics` `DL/CNN`
  `DL/Compression` `DL/Embeddings` `DL/Optimization` `DL/RNN` `DL/Regularization`
  `DL/SelfSupervised` `DL/Transfer` `DL/Transformer` `Eval/Bias` `Eval/Metrics`
  `Feature/Engineering` `Feature/Selection` `ML/Algorithms` `ML/Anomaly`
  `ML/Ensemble` `ML/Imbalanced` `ML/Interpretability` `ML/Supervised`
  `ML/TimeSeries` `ML/Unsupervised` `Math/InfoTheory` `Math/LinAlg`
  `Math/Optimization` `Math/Probability` `Math/Statistics` `Modeling/Selection`
  `Privacy/Compliance` `RL/RewardShaping` `Training/Calibration` `Training/Tuning`
  `Training/Validation`
  （`DL/Compression` 與 `RL/RewardShaping` 是 2026-08-08 新增，各僅 1 題覆蓋；
  若後續仍只有各 1 題，可考慮併回 `DL/Optimization` / `ML/Algorithms`）

## 已知瑕疵（查過了，刻意不修，別重新調查）

- **114 年 B3 Q49**：選項 A 疑似缺一張行內數學式小圖，屬原始 PDF 本身的問題。
- **115 年 `exam-s1-115-1-q28`**：選項 D 開頭的 `「` 在 PDF 文字層裡就不存在
  （核對過是真的缺，不是抽取程式漏抓），刻意不補；同題選項 A 是字元順序錯位，
  已重排成正確順序。
- **s2 / e1 / e2 的既有品質問題**（如 `guide-*` 200 題選項長度 100% 偏長）：
  不在維護範圍，不修。

---

# 階段二，一直複習後，覺得某方面概念不熟悉，再想辦法從原始pdf產生新QA
（暫時不做）
