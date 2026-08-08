# 專案說明（常駐參考 — 後續 agent 動手前先讀這一節）

## 這是什麼

iPAS AI 應用規劃師的考古題練習 app。**一個自給自足的靜態 `index.html`**，
使用者雙擊就能開（`file://`），不需要 server、不需要 build、不連任何後端。
作答記錄存在瀏覽器 `localStorage`，不上傳。另有部署到 Vercel。

## 架構（三句話講完）

```
subjects/*/*.json          ← 題庫的「唯一真相」(system of record)
        ↓  build script 合併、驗證、重建
index.html 第 378 行  const POOL = [...]   ← app 實際讀的內嵌陣列
        ↓
localStorage               ← 只存作答記錄，與題庫無關
```

`index.html` **沒有任何 `fetch()`**。第 378 行是單獨一整行、約 66 萬字元的 JS
常數字面量（`const POOL = [` 開頭、`];` 結尾），是全檔唯一的資料區；其餘
1311 行都是樣式與邏輯，改題庫時完全不該碰。

## 檔案地圖

| 路徑 | 說明 |
|---|---|
| `index.html` | app 本體。資料在 `:378`，其餘是程式 |
| `index.html:382` `SUBJECTS` | 五個科目的中繼資料（`s1 s2 s3 e1 e2`） |
| `index.html:537` `pdfHref()` | 把 `source.file` 組成 `#page=N` deep link |
| `index.html:565` `poolForSubject()` | 純靠 `q.subject_code` 過濾科目 |
| `index.html:658` `translateExplanation()` | 選項打亂時重寫解析裡的 A/B/C/D |
| `subjects/<科目>/progress.json` | 既有題庫（5 檔，共 795 題） |
| `subjects/<科目>/past-exam*.pdf` | 官方歷屆試題，`source.file` 指向它 |
| `subjects/<科目>/study-guide.pdf` | 學習指引，寫 `explanation` 的依據 |
| `shared/sample-questions.pdf` | 官方樣題（涵蓋中級三科） |
| `shared/images/` | 圖表題的裁切圖 |
| `source_pdfs/` | 原始 PDF 暫存區（**untracked**，不進 git） |
| `tools/build_pool.py` | JSON → `index.html:378` 重建 POOL。`--check` 驗同步 |
| `tools/extract_exam.py` | 官方 PDF → `exam-*.json`（三階段，checkpoint 可重跑） |
| `tools/tests/test_golden_answers.py` | 對 114 年兩科 100 題的回歸測試 |

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
   - 錯誤選項條列寫 `- A. …` 單字母。⚠️ 修正：`- A/B. …` 合併其實**已經被支援**
     （`17fa64e` 讓 Pass 2 regex 吃任意數量的 `/`，Pass 3 也會排序），既有
     `exam-114-2-q10` 就是這樣寫的。所以這條是**風格偏好，不是硬約束**，
     `build_pool.py` 只會給 Warning 不會擋。
4. **`topic` 要沿用既有詞彙**（s1 有 47 種、s3 有 33 種，清單見 §3.8），不要自由
   發明，否則科目篩選的 topic 清單會碎片化。
5. **`id` 必須跨全部 json 唯一**，不能只檢查同一個檔案內。
6. **`subject_code` 每題都要填**。`poolForSubject()` 純靠這欄過濾，缺了在「依科目
   篩選」時題目會消失。注意 `1-ai/progress.json` 連 top-level 都沒有這欄。
7. **`source.file` 必須是 ASCII 相對路徑**（會被拿去組 URL）。PDF 進 repo 前要
   改成 `past-exam-115-1.pdf` 這種乾淨檔名，不要留中文長檔名。
8. **絕不引入 OCR**。這批 PDF 的文字層是乾淨的，一律直讀。實測過 OCR-based 抽取
   在繁體中文上會靜默改字（錯字率 20.7% vs 直讀 0.6%）且慢 12 倍。
9. **改完 json 一定要重建 POOL**。只改 json 不重建，使用者端看不到任何變化——
   `0b952e7` 就是漏了這步，造成 298 題 drift 三個月沒被發現。
10. **圖表題的圖要裁掉答案欄**再存進 `shared/images/`，不要放整頁截圖。
11. **不要動 `localStorage` 的 schema**（`test-prep-rounds-v1`），會清掉使用者的
    歷史作答記錄。

## 目前的維護範圍

| 科目 | 代碼 | 狀態 |
|---|---|---|
| 中級科目一 · AI 技術應用與規劃 | `s1` | ✅ **主要維護對象** |
| 中級科目三 · 機器學習技術與應用 | `s3` | ✅ **主要維護對象** |
| 中級科目二 · 大數據處理分析與應用 | `s2` | ⏸ 不在考試範圍，既有 165 題留著不動，不再新增 |
| 初級科目一 / 科目二 | `e1` `e2` | ⏸ 使用者不會用到，既有 300 題留著不動，已知品質問題不修 |

「留著不動」= 題目繼續留在 POOL 裡給別的使用者用，但不投入維護、統計時要分開列。

## 快速自我檢查

**現在請直接用 `uv run --project tools python tools/build_pool.py --check`**（同步就
exit 0）。下面這段是不依賴 `tools/` 的獨立版本，保留當作交叉驗證用：

```python
import json, glob, collections

# 1. 從 index.html 剖出 POOL（第 378 行的 JS 陣列字面量就是合法 JSON）
src = open("index.html").read()
start = src.index("const POOL = [") + len("const POOL = ")
depth = 0; j = start; instr = False; esc = False
while j < len(src):
    c = src[j]
    if instr:
        if esc: esc = False
        elif c == '\\': esc = True
        elif c == '"': instr = False
    else:
        if c == '"': instr = True
        elif c == '[': depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0: break
    j += 1
pool = {q["id"]: q for q in json.loads(src[start:j+1])}

# 2. 合併所有 json
allq = []
for f in sorted(glob.glob("subjects/*/*.json")):
    allq += json.load(open(f))["verified_question_pool"]

# 3. 逐欄比對
print("POOL", len(pool), "題 / JSON", len(allq), "題")
dup = [k for k, v in collections.Counter(q["id"] for q in allq).items() if v > 1]
print("重複 id:", dup or "無")
print("只在 JSON:", sorted({q["id"] for q in allq} - set(pool)) or "無")
print("只在 POOL:", sorted(set(pool) - {q["id"] for q in allq}) or "無")
for k in ["topic","question_text","options","correct_answer","source",
          "explanation","image","verified","subject_code"]:
    n = sum(1 for q in allq if q["id"] in pool and q.get(k) != pool[q["id"]].get(k))
    print(f"  {k:16s} {n} 題不一致")
```

**目前（2026-08-08，`build_pool.py` 重建後）的實際輸出**：

```
POOL 795 題 / JSON 895 題
重複 id: 無    只在 JSON: 100 題    只在 POOL: 無
  subject_code     195 題不一致   ← ⚠️ 永遠會是 195，不是 bug，見下
  其餘欄位          0 題不一致    ← ✅ 298 題 drift 已抹平
```

- **`options` 298 / `explanation` 102 的 drift 已解決**（`0b952e7` 三個月前改在 JSON、
  沒送進 `index.html` 的那批）。`build_pool.py` 從 JSON 重建，答案一個字都沒動。
- **「只在 JSON: 100 題」是預期的**：`subjects/{1-ai,3-ml}/exam-115-1.json` 的 115 年
  新題還沒填 `topic`/`explanation`，`verified: false`，`build_pool.py` 會跳過不收進 POOL。
  填完並翻成 `verified: true` 之後，這裡就會變成 0、POOL 變 895 題。
- **`subject_code` 的 195 題會永遠停在 195**。上面這段獨立 script 是直接比對「JSON 原文」
  vs POOL，而 `build_pool.py` 的目錄對照表補值是**在記憶體裡做的、不寫回 JSON**
  （其中 65 題屬 `2-bigdata`，紅線禁止改該檔）。所以這欄不一致是設計使然。
  想看真正的同步狀態請用 `build_pool.py --check`（它比對的是補值後的結果，該欄為 0）。
- **其餘每一欄都必須是 0**，特別是 `correct_answer` ——它不是 0 就代表有人動了
  答案，屬於嚴重問題。

---

# 資料更新規劃
## 階段一，補上新的歷屆考題
- 理解 repo 產生題目的邏輯，分析json檔案，從歷史的git log分析，為什麼這樣設計題目，包含哪些keys? 如果要把新的資料補進去，有哪些需要注意 o
- 解析 pdf ，參考過去的抽取程式，寫一個新的script把歷屆考題抽出來，製作成新的json
- 讓程式讀檔的時候，自動合併該目錄底下的所有json，確保抽選題目的時候從這些json抽

### 分析結果（2026-08-08）

> **範圍註記**（完整範圍見〈專案說明 · 目前的維護範圍〉）：本節的分析與數字涵蓋
> 中級三科 `1-ai` / `2-bigdata` / `3-ml`（495 題），**不含** `entry-1-ai` /
> `entry-2-genai`（初級兩科）——它們已知的資料問題**不修**。
> 註：`2-bigdata`（s2）後來也確定不在考試範圍，既有題目留著不動、不再新增，
> 但本節分析當時已把它算進去，數字照列。

#### 資料流程（目前的樣子）

```
subjects/*/progress.json  (人工/AI 產生、驗證 → 「系統記錄」)
        ↓ 手動合併、補 subject_code、貼進去（沒有 script！）
index.html 第 378 行  const POOL = [...]   ← app 實際讀的是這個內嵌 array
        ↓
localStorage（只存作答記錄/rounds，跟 progress.json 無關）
```

**關鍵發現：`index.html` 完全沒有 `fetch()`。** 五個 `progress.json` 的
`verified_question_pool` 內容是被人工/AI 攤平、拼接成一個 795 題的 JS 常數
字面量，直接寫死在 `index.html` 裡。commit `54e444b` 的說明也印證這點：
「Tracker JSONs are the system of record for verified pools; ... Quiz
runtime state lives in localStorage and is independent of these.」

`progress.json` 裡的 `rounds` / `weak_topics` 是某次作答會話留下的存檔快照，
`index.html` 完全不讀它們，不是 app 運行時會用的東西。

➡️ 這正好對應到本階段第三點想做的事：目前**完全沒有**「讀檔時自動合併
目錄底下所有 json」的機制，是要新建的功能。這是新增資料前最需要處理的
架構缺口，不然新題目加進 `progress.json` 也不會出現在 app 裡。

**⚠️ 而且這個手動流程已經漏掉一次，兩邊現在是 drift 的：**

| 比對 `progress.json` vs `index.html` POOL | 不一致題數 |
|---|---|
| `options` | 298（1-ai 100、2-bigdata 98、3-ml 100，全是 `gen-*`） |
| `explanation` | 102（是上面 298 的子集） |

原因：commit `0b952e7`（選項長度平衡）**只改了 3 個 `progress.json`，沒有
同步改 `index.html`**（`git show --stat 0b952e7` 只列出 3 個 json）。所以
「system of record 是 JSON」這句話目前不成立——兩邊誰是真的要逐欄看。
詳見文末〈已發現的既有問題〉。

#### `progress.json` 完整 schema

**頂層 keys**（5 個檔案不完全一致）：

| key | 1-ai | 2-bigdata/3-ml | entry-1/2 | 說明 |
|---|---|---|---|---|
| `version` | ✓ | ✓ | ✓ | 固定 1 |
| `test_name` | ✓ | ✓ | ✓ | 科目全名 |
| `subject_code` | ✗（缺） | ✓ (`s2`/`s3`) | ✓ (`e1`/`e2`) | 1-ai 這份沒有，歷史遺留 |
| `subject_short` | ✗ | ✓ | ✓ | 簡稱 |
| `source_files` | ✓ | ✓ | ✓ | 來源 PDF 檔名 array |
| `verified_question_pool` | ✓ | ✓ | ✓ | 題目本體 |
| `rounds` | ✓ | ✓ | ✗（entry 沒有） | 作答存檔快照，app 不讀 |
| `weak_topics` | ✓ | ✓ | ✗ | 同上 |

**單題 keys**：

| key | 必填 | 說明 |
|---|---|---|
| `id` | ✓ | 全庫（跨 5 個檔案）必須唯一，目前 795 題無重複（已驗證） |
| `topic` | ✓ | 慣例是 `分類/子分類`，如 `NLP/Transformer`、`Risk/Privacy`。**但不是硬規則**：795 題中有 88 題是單層（`NLP`、`CV`、`Privacy`…），中級三科佔 43 題。`getTopics()` 只做字串 groupby，單層不會壞 |
| `question_text` | ✓ | 題幹 |
| `options` | ✓ | `{A,B,C,D}` dict |
| `correct_answer` | ✓ | 單一字母 |
| `source` | ✓ | `{file, page, evidence}` — 出處 + 佐證文字 |
| `verified` | ✓ | 目前全部是 `true` |
| `verification_needed` | ✓ | 全部是 `null`，預留給未來未驗證題用 |
| `explanation` | ✓ | Markdown：為什麼對 + 每個錯選項為什麼錯 + 記憶要點，三段式固定格式 |
| `image` | 選填 | 極少數圖表題才有，指向 `shared/images/*.png` |
| `subject_code` | JSON 側部分才有；**POOL 側 795 題全有** | JSON 裡缺 195 題（1-ai/2-bigdata/3-ml 的 `exam-*`+`sample-*` 各 65 題）；人工攤平進 `index.html` 時被補齊，所以 app 目前沒壞 |
| `generated` | 僅 AI 生成題 | `true` |
| `generated_by` | 僅 AI 生成題 | `"claude"` / `"codex"` |

**id 前綴規則**（用來分辨題目來源）：
- `exam-*` / `entry-*`：官方歷屆考題（人工核對答案欄）
- `sample-*`：官方樣題
- `gen-*` / `guide-*`：AI 依據 study-guide 生成的補充題

#### 為什麼這樣設計（從 git log 讀出的動機）

- **`source` + `evidence`**：`d162241` 把 PDF vendor 進 repo 的理由是「可驗證、
  可重現答案」——每題都要能回溯到官方答案欄或權威來源（GDPR/OWASP/arxiv 等）。
- **`explanation` 固定三段式**：方便「💡 為什麼？」面板統一渲染，也方便選項
  shuffle 時用 regex 重寫字母對應（`d155b72`、`17fa64e` 兩次修 bug 都在處理
  「解釋文字裡的 A/B/C/D 要跟著顯示順序換」的一致性問題）。
- **`generated` / `generated_by`**：`2451109` 加入 AI 補充題時特地標記來源
  （claude vs codex），UI 上用「✨新題」綠色徽章區分官方題與 AI 補的題。
- **`0b952e7` 選項長度平衡**：AI 生成的 300 題一開始有「正解選項最長」的
  作弊線索（最高 91% 命中率），重寫全部選項讓長度比控制在 1.4x 內。
  ⚠️ **但這次修正只落在 `progress.json`，`index.html` 沒同步**——實際跑的
  app 至今仍是修正前的選項（tell 率 206/300 = 69%）。
- **`image` + `source.page`**：`3f88e1e`/`cc8aa4a` 處理圖表題——裁切成單題
  範圍、並用白色色塊遮住 PDF 裡的「答案欄」，避免圖片本身洩漏答案。
- **`rounds`/`weak_topics`（僅中級三科有）**：早期人工陪練時留的存檔，屬於
  歷史遺留，app 本身用 localStorage 自己管理，不依賴這些欄位。

#### 補新資料時要注意的事項

1. **id 必須全庫唯一**——跨全部 5 個 `progress.json` 檢查，不能只看同一個
   檔案內。
2. **`subject_code` 一定要每題都填**。`poolForSubject()`
   （index.html:565-568）純靠 `q.subject_code` 過濾，缺了這欄，題目在
   「依科目篩選」時會消失，只能在 `subjectFilter === "all"` 才看得到。
   目前 app 沒壞（POOL 795 題全有），但 JSON 側缺 195 題，代表**這欄是靠
   人工攤平時補的**。做自動合併時要注意：`1-ai/progress.json` 連 top-level
   都沒有 `subject_code`，所以 script 不能只靠「讀 top-level 灌進每題」，
   得有目錄名 → 代碼的對照表（`1-ai`→`s1`、`2-bigdata`→`s2`、`3-ml`→`s3`）。
3. **`options` 長度要平衡**，避免「正解永遠最長」的選項長度 tell（可參考
   `0b952e7` 的做法：正解/最短選項 ≤1.4x）。
4. **`explanation` 要照三段式模板**（為什麼X是正解 / 其他選項為何錯 /
   記憶要點），錯誤選項條列要用 `- A. ...` 單字母格式（不要用 `A/B/C.`
   合併寫法），否則會踩到 `d155b72` 修過的 shuffle 重寫 bug。
5. **`source.evidence` 要寫清楚可驗證的依據**（官方答案欄頁碼，或具體的
   權威來源網址/文件），維持「每題都可回溯」的設計初衷。
6. **最關鍵的一步：把新題目實際接進 `index.html` 的 `POOL`**——目前沒有
   自動合併機制，新增 `progress.json` 內容後仍需要手動/寫 script 把它拼進
   `index.html:378` 的常數（或者先做本階段第三點規劃的「自動合併目錄下所有
   json」功能，這樣以後加題目就不用碰 `index.html` 了）。**`0b952e7` 就是
   漏掉這步才造成現在的 drift**，所以這步不能靠記憶，要嘛自動化、要嘛加
   一個「JSON vs POOL 逐題比對」的檢查 script。
7. **圖片題**：若有配圖，圖片要先做「裁切到單題範圍 + 遮答案欄」處理再放
   進 `shared/images/`，不要直接放整頁 PDF 截圖。

#### 已發現的既有問題（查證時翻出來的，非規劃內）

**A. `index.html` 沒吃到選項平衡修正 —— ✅ 2026-08-08 已解決**

> `tools/build_pool.py` 從 JSON 重建 POOL，一次抹平全部 298 題（`options` 298、
> `explanation` 102，100% 是 `gen-*`，官方題 0 題，`correct_answer` 0 題變動）。
> 以下保留原始分析當作紀錄與「為什麼要做 build script」的依據。

`0b952e7` 只改 JSON、沒改 `index.html`，所以線上 app 的 `gen-*` 300 題仍是
舊版選項。用該 commit 自己的指標（正解比最長干擾項長 ≥3 字）重算：

| | JSON | index.html POOL |
|---|---|---|
| `gen-*` 300 題長度 tell | 44 (15%) | **206 (69%)** |

（比對用的其他題組兩邊一致：`exam-*` 58/150、`sample-*` 11/45，無 drift。）

**`index.html` 是乾淨的舊版快照，不是壞掉的混合體**——POOL 與
`0b952e7^` 的 JSON 逐題比對，中級三科 495 題的 `options` 與 `explanation`
**495/495 完全相同**。所以畫面上不會出現「選項是新的、解析講的是舊的」，
使用者看到的是一個前後一致、但沒吃到修正的版本。

**使用者實際會遇到的狀況：**

1. **不用讀題也能猜對**——「永遠選最長的選項」在 app 現況下的命中率：

   | 題組 | 命中率 |
   |---|---|
   | `gen-*` AI 補充題（300 題） | **76%** |
   | `exam-*` 官方歷屆（150 題） | 49% |
   | `sample-*` 官方樣題（45 題） | 40% |
   | 中級三科全池 495 題 | **65%**（隨機猜 = 25%） |

   官方題本來就有 ~49% 的自然偏長現象，`gen-*` 的 76% 是明顯異常。
   若換成 JSON 修好的版本，`gen-*` 會降到 48%，回到官方題水準。

2. **「隨機打亂選項」擋不住這個問題**——`shuffle()`（index.html:591）只換
   A/B/C/D 的位置，最長的選項洗完還是最長，長度線索完全不受影響。

3. **練習分數虛高，對考試準備度產生誤判**——一輪 25 題若抽到較多 `gen-*`，
   分數會被長度線索灌水；`d9d160e` 的 70% 灑花甚至可能是靠猜長度觸發的。

4. **弱點分析會失準**——`getWeakTopics()` 靠答錯率統計，靠長度猜對的題目
   會讓該 topic 看起來已經掌握，`2fa2fb9` 的「重複出錯題加權」也就不會把
   真正不熟的題目再推出來。連帶影響階段二「找出不熟概念」的判斷基礎。

5. **現在改 `progress.json` 不會有任何效果**——階段一補的新題若只進 JSON、
   沒重建 POOL，使用者端看不到任何變化。

為什麼要先修：階段一第三點的自動合併一旦做出來，就等於要選定「以 JSON
為準」，屆時這 298 題會被 JSON 版本覆蓋掉——這其實正是想要的結果，但要
先確認 JSON 版本的 `explanation` 與新選項對得上（102 題有一起改），不然
會出現「選項是新的、解釋是舊的」的混搭。**建議做法：直接讓自動合併
script 從 JSON 重建 POOL，一次把 drift 抹平，而不是逐題手動 patch。**

**B. entry 兩科的 `guide-*` 200 題長度 tell 是 100% —— 已決定不修**

`3d20c14`（晚於 `0b952e7`）加入時沒套用選項平衡：

- 200/200 題正解都是最長選項
- 正解 / 干擾項平均長度比 **2.89x**（官方 `entry-*` 題是 1.12x）
- 干擾項多為極短的絕對化句子。例 `guide-e2-q046`：正解 46 字，其餘為
  「完全不需要治理」(7)、「一定能取代所有專業程式開發」(13)、
  「封閉平台不會造成鎖定風險」(12)

因初級兩科不在使用範圍內，**此項不處理**，僅留紀錄。若日後自動合併把
entry 目錄一起吃進來，要記得這 200 題品質偏低。

#### 已驗證無誤的部分（可信賴，不需重查）

`fetch()` / `XMLHttpRequest` 皆為 0；JSON 與 POOL 的 795 個 id 集合完全
一致且無重複；`source` 的 `{file, page, evidence}` 三欄 795/795 齊全；
`explanation` 三段式（為什麼 / 其他選項為何錯 / 記憶要點）795/795 齊全；
`options` 全部是 `{A,B,C,D}`；`verified` 全 `true`、`verification_needed`
全 `null`；POOL 內已無 `- A/B.` 合併字母 bullet（`d155b72` 修乾淨了）；
19 題有 `image`，對應 `shared/images/` 的 19 個檔；本文引用的 8 個 commit
hash 全部存在且描述相符。

---

# 階段一 實作計畫（2026-08-08 定案）

## 0. 已定案的決策

| 決策 | 選擇 | 理由 |
|---|---|---|
| 合併機制 | **build script 重建 POOL** | README 承諾「雙擊 index.html 就能開、不用 server」。runtime `fetch()` 在 `file://` 下會被 CORS 擋死，等於毀掉離線雙擊體驗 |
| entry 兩科 | **照收進 POOL，維持現狀** | app 內容不變；`guide-*` 的品質問題已記錄、不修 |
| 新考題檔案配置 | **每次考試一個新檔**（`exam-115-1.json`） | 既有 `progress.json` 完全不動；正是「自動合併目錄下所有 json」要的形態 |
| 官方題選項 | **逐字保留，永不做長度平衡** | 官方題的長度偏長是真實考題的性質，「修正」等於偽造素材 |

**這次新增的資料範圍**：只做**科目一、科目三**，各 50 題 → POOL 從 795 題增加到
**895 題**。

> **科目二不做**（2026-08-08 使用者確認：不在考試範圍）。115 年第一次本來也沒有
> 科目二的公告試題。既有的 165 題 s2 比照 entry 兩科處理——**留在題庫裡不動，
> 但不再新增、不再投入維護**。以後有新考題也不抽科目二。

## 1. 產出物

```
tools/                          ← 新增（開發用，使用者不需要碰）
├── pyproject.toml              # uv 專案定義，requires-python = ">=3.12"
├── uv.lock                     # 相依版本鎖定
├── .python-version
├── extract_exam.py             # PDF → exam-*.json
├── build_pool.py               # subjects/**/*.json → index.html:378
└── tests/
    └── test_golden_answers.py  # 對 114 年兩科做回歸測試（見 §5）

subjects/1-ai/
├── past-exam-115-1.pdf         # 新增（從 source_pdfs 複製、改成 ASCII 檔名）
└── exam-115-1.json             # 新增，50 題
subjects/3-ml/
├── past-exam-115-1.pdf
└── exam-115-1.json
shared/images/                  # 新增 A3 的程式碼截圖（見 §3.6）
```

執行方式：`uv run --project tools python tools/extract_exam.py ...`

**相依套件只需要 `pdfplumber`**（文字 + 座標 + 表格 + `to_image()` 裁圖都夠用）。
PyMuPDF 先不加。

> **⚠️ 從參考專案學到、務必遵守的一條**：`/home/lawrencechh/j/evaluate_translation/`
> 那套 pipeline 實測過，`unstructured` 的 `hi_res` OCR 模式在**繁體中文 PDF 上會用
> 視覺辨識結果覆寫原本乾淨的文字層**，產生「落實→洛實、情蒐→情葯」這類**靜默
> 錯字**，錯字率 20.7%（規則式抽取只有 0.6%），而且慢 12 倍。
> **本專案的 PDF 文字層是乾淨的，一律直讀文字層，絕不引入任何 OCR 路徑。**

## 2. 已實測驗證的關鍵事實

寫程式前先確認過的（探測腳本在 scratchpad，可重跑）：

| 事實 | 驗證結果 |
|---|---|
| 四份 PDF 都有乾淨文字層 | ✅ 非掃描檔，`extract_text()` 正常 |
| 版面是「答案｜題目」兩欄表格，貫穿全文件 | ✅ 有真實框線，`find_tables()` 抓得到 |
| 每份剛好 50 題，題號 1~50 連續無缺 | ✅ A1/A3/B1/B3 皆是 |
| 座標分欄能精準抓答案 | ✅ 左欄（`x0 < 100`）過濾後**恰好 50 個單字母**，零誤判零遺漏 |
| 表格列 = 一題 | ✅ 表頭獨立成 row0，其餘每 row 一題 |
| 頁首/頁尾會自動被排除 | ✅ 它們落在表格 bbox（y≈89~794）之外 |
| 浮水印圖 bbox 固定 | ✅ 每頁都是 `(102.5, 365.1, 492.8, 528.8)`，直接黑名單 |
| 新舊版格式一致，可共用同一套程式 | ✅ 僅三處差異，見 §4 |

**最重要的驗證**：用座標法抽 114 年兩科的答案，跟 repo 裡 100 題**人工核對過**的
`correct_answer` 逐題比對——

```
B1 (114 科一): 人工核對 vs 座標抽取  ✅ 50/50 完全一致
B3 (114 科三): 人工核對 vs 座標抽取  ✅ 50/50 完全一致
```

這 100 題就是現成的 golden test，抽取程式必須先通過它，才能信任它跑 115 年的新檔。

## 3. `tools/extract_exam.py` 設計

### 3.1 CLI

```
uv run --project tools python tools/extract_exam.py \
    --pdf   source_pdfs/115年第一次..._第一科_....pdf \
    --subject s1 \
    --exam-id 115-1 \
    --out   subjects/1-ai/exam-115-1.json \
    --pdf-dest subjects/1-ai/past-exam-115-1.pdf \
    --image-dir shared/images
```

參考 `run_pipeline.py` 的分階段設計，中繼檔即 checkpoint、可單獨重跑：

```
stage 1  parse    PDF → raw_rows.json     （表格列 + 座標，deterministic）
stage 2  assemble raw_rows.json → questions.json（切題、拆選項、配圖）
stage 3  emit     questions.json → exam-115-1.json（套 schema、驗證）
```

抽取產物是決定性的，改下游邏輯時不必重抽（這是參考專案明文記載的教訓）。

### 3.2 切欄（核心演算法）

**不要用 regex 掃 `extract_text()` 的行**——答案字母與題號會被插進題幹中間，
而且插法不規律（Q1 是 `1.`\n`D` 分兩行，Q2 是 `C 2.` 同一行）。改用座標：

1. `page.find_tables()` 取得該頁唯一的表格與每個 row 的 bbox
2. row0 是表頭（含「答案」「題目」字樣）→ 丟棄
3. 欄界線取表格的第二條垂直線（實測 A1≈84.6、A3≈81.1、B1≈100、B3≈90）
   ——**動態從 `table.rows[*].cells` 讀，不要寫死**
4. 每個 row 內：`x0 < 欄界` 的字 = 答案欄；`x0 >= 欄界` 的字 = 題目欄

### 3.3 切題規則

以表格 row 為單位，依「答案欄有沒有字母」與「題目欄有沒有題號」分三類：

| row 型態 | 判定 | 處理 |
|---|---|---|
| 答案欄有字母 + 題目欄有 `^\d+\.` | 新的一題 | 開新題 |
| 兩者都沒有 | 前一題的跨頁續行 | 併入前一題（例：A1 Q20 從 p.6 跨到 p.7） |
| 題目欄含 `回答第 X~Y 題` | 共用題幹 | 敘述複製給 X~Y 每一題 |

### 3.4 答案正規化（**必做**）

答案欄混了**全形拉丁字母**（打字的人開著全形輸入法）：

```
A1: Ｄ 50.        A3: Ｂ 44.  Ａ 45.        B3: Ｃ 48.  Ｃ 49.  Ｃ 50.
```

字型也不一樣（全形的是楷書 `DFKaiShu`，正常的是 `TimesNewRomanPSMT`）。
一律 `unicodedata.normalize("NFKC", …)` 後才比對，否則 `answer == "D"` 會漏掉 `"Ｄ"`。
**新舊版都有這問題，不是 115 年才出現的。**

### 3.5 拆選項

- 選項標記固定是**半形** `(A)(B)(C)(D)`，各自獨立成行（不是兩欄排列）
- **`regex` 不可以用 `[(（]` 同時吃兩種括號**：題幹大量出現全形括號包術語
  （`（Information Extraction）`、`（Domain Fine-Tuning）`），會誤判
- 只在**行首**匹配 `^\(([A-D])\)`，且只認 A-D 四個字母
- 選項文字常自動換行 → 下一個 `(X)` 出現前的所有行都併進當前選項
- 行尾的分隔符 `；` 要去掉
- 題幹自己會用 `(1)(2)(3)` 清單（A1 Q20），選項文字裡也會引用 `(1)(2)(3)`
  ——因為只認 A-D，這個不會誤傷，但別把規則放寬成「行首括號」

### 3.6 圖表題

先確認的清單（浮水印**不算**）：

| 檔 | 題號 | 內容 |
|---|---|---|
| A1 | Q19 | 指標對照表截圖（AUC/CTR/訂單金額） |
| A3 | Q40, Q41 | Keras / PyTorch 程式碼截圖（Q40 含填空 `___(A)___`） |
| A3 | Q42-43 | ResNet 遷移學習程式碼（共用題組） |
| A3 | Q44-45 | 5 張圖：情境、`ucimlrepo` 程式碼、DataFrame 輸出 ×2、候選片段 |
| A3 | Q46-48 | CIFAR-10 資料處理 + 模型結果（共用題組） |
| A3 | Q49-50 | AOI 瑕疵偵測情境圖 + 訓練迴圈位置示意圖（共用題組） |

全部是**點陣截圖**（`page.images` 有 `srcsize`），不是向量圖。處理方式：

1. 過濾掉浮水印（bbox 完全等於 `(102.5, 365.1, 492.8, 528.8)`）
2. 用「圖片 bbox 落在哪個 row 的 y 區間」自動對應到題號
3. 裁切範圍取 **row bbox ∩ 題目欄 x 區間**——這樣**答案欄天然被切在框外**，
   自動達成 `cc8aa4a` 當初手工做的「遮住答案欄」要求，不必再另外塗白
4. `page.crop(bbox).to_image(resolution=200).save()` 存到 `shared/images/`
5. 命名照既有慣例：`exam-s3-115-1-q40-p11.png`

**數學式是純文字不是圖**（有上下標），但下標會造成假分行（A3 Q3 抽出來會有孤立的
`Q` 單字行），組行時要用 y 容差合併，不能假設「一行一句」。

### 3.7 輸出 schema 與 `explanation` 的處理

沿用既有 schema（§ 前面的「單題 keys」），並且：

- `id`：`exam-s1-115-1-q1` … / `exam-s3-115-1-q1` …
  （既有 s1 是 `exam-114-2-q1` 沒帶科目、s3 是 `exam-s3-114-2-q1` 有帶，屬歷史
  不一致。新的一律帶科目代碼，比較好認，且不會跟任何既有 id 相撞）
- `subject_code`：**每題都填**，不留給下游補
- `source.file`：`subjects/1-ai/past-exam-115-1.pdf`（**必須 ASCII**，
  `pdfHref()`（index.html:537）會拿去組 `#page=N` deep link）
- `source.page`：PDF 實體頁碼
- `source.evidence`：`answer column shows 'D' for question 50`（沿用既有措辭）

**`explanation` 不可能由 parser 產生**，它是三段式的教學文字。所以抽取程式輸出時：

```json
"explanation": null,
"verified": false,
"verification_needed": "explanation"
```

`verification_needed` 這個欄位在 795 題裡一直是 `null`（預留未用），**這次終於用上
它原本的設計目的**。流程分兩步：

1. `extract_exam.py` 產出機械可得的部分（題幹/選項/答案/出處），`verified: false`
2. 另一輪（AI 或人工）補 `explanation`，通過後才翻成 `verified: true`

`build_pool.py` **只收 `verified: true` 的題目**，未完成的會被跳過並列在摘要裡。
這樣半成品可以安全地 commit 進 repo，不會污染 app。

### 3.8 欄位分工：哪些是 parser 產的、哪些要 agent 填

**只有兩個欄位需要另一輪 agent 填寫**，其餘全部機械可得：

| 欄位 | 產生者 | 說明 |
|---|---|---|
| `id` | parser | 依題號生成 `exam-s1-115-1-q1` |
| `question_text` | parser | 題目欄逐字抽取 |
| `options` | parser | 行首 `(A)`~`(D)` 切分 |
| `correct_answer` | parser | 答案欄座標抽取（已驗證 100/100 準確） |
| `source.file` / `.page` | parser | PDF 路徑 + 實體頁碼 |
| `source.evidence` | parser | 固定句型 `answer column shows 'D' for question 50` |
| `image` | parser | 裁圖並自動對應題號 |
| `subject_code` | parser | CLI 參數 |
| `verified` / `verification_needed` | parser | 先填 `false` / `"topic,explanation"` |
| **`topic`** | **agent** | `分類/子分類`，**必須從既有詞彙挑**（見下） |
| **`explanation`** | **agent** | 三段式教學文字（格式硬約束，見 §3.9） |

工作量：100 題 × 2 欄位。

**答案不需要 agent 判斷**——`correct_answer` 直接來自官方答案欄，這是整個設計最可靠
的一環。agent 只負責解釋「為什麼是這個答案」，**不負責決定答案**。若 agent 覺得
官方答案有誤，應該記進 `verification_needed` 提報，而不是自行改 `correct_answer`。

**`topic` 必須沿用既有詞彙**，不可自由發明，否則科目篩選的 topic 清單會碎片化
（`getTopics()` 是純字串 groupby）。現有詞彙：

- **s1（47 種）**：`AI/Adoption` `AI/Definition` `AI/Planning` `AI/Risk`
  `CV/Classification` `CV/Detection` `CV/OCR` `CV/Pose` `CV/Segmentation` `CV/ViT`
  `Data/Augmentation` `Data/Drift` `Data/Preprocessing` `Deploy/Integration`
  `Deploy/Kubernetes` `Deploy/MLOps` `GenAI/Compression` `GenAI/Diffusion`
  `GenAI/FineTuning` `GenAI/GAN` `GenAI/PromptEngineering` `GenAI/RAG`
  `ML/Classification` `ML/Clustering` `ML/Evaluation` `ML/Overfitting` `ML/Regression`
  `Multimodal` `Multimodal/CLIP` `Multimodal/Fusion` `Multimodal/General`
  `NLP/BERT-vs-GPT` `NLP/Embedding` `NLP/General` `NLP/Hallucination` `NLP/LLM-Eval`
  `NLP/NER` `NLP/RAG` `NLP/Sentiment` `NLP/Summarization` `NLP/Tokenization`
  `NLP/Transformer` `NLP/Translation` `Risk/Compliance` `Risk/Copyright`
  `Risk/Privacy` `Risk/Security`
- **s3（33 種）**：`Bias/Fairness` `BigData/Processing` `DL/Basics` `DL/CNN`
  `DL/Embeddings` `DL/Optimization` `DL/RNN` `DL/Regularization` `DL/SelfSupervised`
  `DL/Transfer` `DL/Transformer` `Eval/Bias` `Eval/Metrics` `Feature/Engineering`
  `Feature/Selection` `ML/Algorithms` `ML/Anomaly` `ML/Ensemble` `ML/Imbalanced`
  `ML/Interpretability` `ML/Supervised` `ML/TimeSeries` `ML/Unsupervised`
  `Math/InfoTheory` `Math/LinAlg` `Math/Optimization` `Math/Probability`
  `Math/Statistics` `Modeling/Selection` `Privacy/Compliance` `Training/Calibration`
  `Training/Tuning` `Training/Validation`

真的沒有適合的才新增，且新增時要在摘要裡明確列出，方便回頭檢視是否該併入既有分類。
（注意既有詞彙本身有小瑕疵：s1 同時存在 `Multimodal` 與 `Multimodal/General`，
新題目一律用有斜線的那個。）

**agent 需要的輸入**：題幹 + 選項 + 官方答案 + 對應科目的 `study-guide.pdf`。
既有題目的 `explanation` 都是從學習指引寫出來的，維持「每題都可回溯」的設計初衷。

**交付方式**：`extract_exam.py` 產出的 json 直接就是待填檔（`explanation: null`、
`topic: null`），agent 就地填寫同一個檔案，不需要另外設計中介格式。填完跑
`build_pool.py` 自動驗格式。

### 3.9 `explanation` 的格式約束

**`explanation` 的格式是硬性約束，不只是慣例**：`translateExplanation()`
（index.html:658-697）在「選項打亂」模式下會用 regex 重寫字母對應——

- 標題必須是 `**為什麼 X 是正解:**`（regex `為什麼\s+([A-D])\s+是`，**字母前後要有空白**）
- 錯誤選項條列必須是 `- A. …` 單字母格式，**不可以寫 `- A/B. …` 合併**
  （`d155b72`、`17fa64e` 兩次修的就是這個）
- 必須有「記憶要點」段

## 4. 新舊版格式差異（只有三處，都可規避）

| 差異 | 影響 | 對策 |
|---|---|---|
| 115 年每頁多一張 iPAS 浮水印圖（114 年完全沒有圖） | 圖表題偵測會誤判 | bbox 黑名單，見 §3.6 |
| A3 從 p.11「二、程式題」章節起，**表頭文字自己顛倒**成 `題目 答案` | 若靠表頭字串決定欄位語意就會全錯 | **一律用座標判斷欄位，永遠不讀表頭文字**（實際欄位內容沒變，只是標籤印反，是原始 PDF 的 bug） |
| A3 共用題組變多（3 組 vs 114 年 1 組） | 切題規則要處理 | §3.3 第三類 |

## 5. 驗收標準

**Golden test（必須先過）**：對 114 年兩科跑一次抽取，跟 repo 裡人工核對過的
100 題比對——

1. `correct_answer` 必須 **100/100 完全一致**（已預先驗證此法可達成）
2. `question_text` 與既有 `progress.json` 的相似度需 > 95%（容許空白/標點正規化差異）
3. 題數必須是 50/50

過不了就是抽取邏輯有問題，**不准拿去跑 115 年的新檔**。

**115 年新檔的驗收**：

4. 各 50 題，題號 1~50 連續
5. 每題四個選項都非空
6. 圖表題的圖都存在、且裁切範圍不含答案欄（人工抽看 §3.6 清單裡的每一題）
7. 全形答案字母都已 normalize（A1 Q50、A3 Q44/Q45）

## 6. `tools/build_pool.py` 設計

### 6.1 流程

```
1. glob subjects/*/*.json
2. 讀每個檔的 verified_question_pool
3. 缺 subject_code 的用目錄對照表補：
     1-ai→s1  2-bigdata→s2  3-ml→s3  entry-1-ai→e1  entry-2-genai→e2
   （注意：1-ai/progress.json 連 top-level 都沒有 subject_code，
     所以不能靠「讀 top-level 灌進每題」，必須用這張對照表）
4. 過濾掉 verified != true 的題目（列進摘要）
5. 排序（見 6.3）
6. 全套驗證（見 6.2），有 error 就 exit 1、不寫檔
7. 重寫 index.html 第 378 行
8. 印出摘要
```

`index.html:378` 是**單獨一整行**（66 萬字元，`const POOL = [` 開頭、`];` 結尾），
可以精準只換這一行，其餘 1311 行完全不碰。

### 6.2 驗證項目

**Error（擋下、exit 1）**：

- `id` 跨全部檔案唯一
- 必填 key 齊全（`id` `topic` `question_text` `options` `correct_answer` `source` `explanation`）
- `options` 剛好 `{A,B,C,D}` 且都非空
- `correct_answer` ∈ `options` 的 key
- `subject_code` ∈ `SUBJECTS`（index.html:382 那五個）
- `source.file` 檔案實際存在（相對於 repo root）、`source.page >= 1`
- `image` 有填的話檔案要存在
- `explanation` 格式：有 `**為什麼 X 是`、有「記憶要點」、
  **沒有 `- A/B.` 合併字母 bullet**（踩到 `d155b72` 的 bug）

**Warning（只印、不擋）**：

- 選項長度 tell：**只檢查 `generated: true` 的題目**。官方題（`exam-*`/`sample-*`/
  `entry-*`）直接跳過——它們的長度偏長是真實考題的性質，不該被「修正」。
  這條規則寫進 script 就是為了防止以後有人手滑去改官方題。
- entry 兩科的 `guide-*` 已知 tell 100%，印出時標成「已知豁免、不修」

### 6.3 排序

現有 POOL 的順序是歷史 append 出來的，**不是**目錄排序（科目二的 `gen-*` 100 題
排在科目三後面，因為它是後來 `57beb55` 才加的）。所以要定一個 canonical order：

```
(level: intermediate → entry,
 subject_code: s1 s2 s3 e1 e2,
 來源類別: exam < sample < gen/guide,
 id 自然排序)
```

**代價**：第一次跑會把整個陣列重排，textual diff 會很大。這只影響 diff 可讀性，
不影響行為（app 本來就是隨機抽題）。驗證正確性時**要用 id 當 key 比對 dict，
不要比對序列**。

### 6.4 第一次執行的預期結果（自我檢查）

從 JSON 重建 POOL 時，會變動的內容應該**剛好等於**下表，多一題少一題都代表有 bug：

| 欄位 | 變動題數 |
|---|---|
| `options` | 298 |
| `explanation` | 102（是上面 298 的子集） |
| `correct_answer` | **0** |
| `question_text` / `topic` / `source` / `image` / `verified` | **0** |

```
受影響題目：298 題，100% 是 gen-*（1-ai 100、3-ml 100、2-bigdata 98）
其中官方題（exam-* / sample-* / entry-*）：0 題
```

這 298 題就是 §「已發現的既有問題 A」講的 drift——**不是這次新寫的修改，是
`0b952e7` 三個月前就改好、只是沒送進 `index.html` 的內容**。重建 POOL 等於讓
app 追上既有修正，答案一個字都不會動。

### 6.5 `--check` 模式

`build_pool.py --check` 重算一次但不寫檔，若 `index.html` 與 JSON 不同步就
exit 1。掛成 pre-commit hook 或 CI，**這次 drift 就是漏跑這一步造成的，不能靠記性**。

## 7. 執行順序

1. 建 `tools/` + uv 環境（`pyproject.toml`、`uv.lock`、`.python-version`）
2. 寫 `build_pool.py` + 驗證邏輯，**先對現有 795 題跑一次**，比對 §6.4 的預期
   ——先確立「JSON 是唯一真相」再談新增資料
3. 寫 `extract_exam.py`，用 114 年兩科過 golden test（§5 第 1-3 點）
4. 跑 115 年科一 → `subjects/1-ai/exam-115-1.json`（`verified: false`）
5. 跑 115 年科三 → `subjects/3-ml/exam-115-1.json`，處理 11 題圖表題
6. 人工抽查圖表題裁切與共用題組切分
7. **agent 填 `topic` + `explanation`**（同一輪做完，見 §3.8），翻 `verified: true`
8. 跑 `build_pool.py` → POOL 895 題
9. 更新 README（題數、`tools/` 說明、新的 PDF 檔案）

**第 2 步刻意排在新增資料之前**：drift 沒抹平就加新題，等於在兩個互相矛盾的
真相來源上疊東西。

## 8. 未決事項

- **樣題**：這四份「公告試題」PDF 只有 50 題官方考題，**不含樣題**。既有的 45 題
  `sample-*` 來自 `shared/sample-questions.pdf`（114年9月版）。115 年有沒有對應的
  新樣題檔案，需要確認。
- **B3 Q49 的資料瑕疵**：選項 `(A)activation="relu"其數學式為 ；` 後面像是缺了一張
  行內數學式小圖，是原始 PDF 本身的問題。這題屬於既有 114 年資料，不影響本次。
- **115 年科一 Q28 的 PDF 缺字**：`exam-s1-115-1-q28` 選項 D 抽出來是
  `負債比率」SHAP 值+1.8…`，開頭的 `「` 在**原始 PDF 的文字層裡就不存在**（已核對）。
  同一題選項 A 的 `(A「) 月收入」` 是字元順序錯位（字都在，只是位置錯），抽取程式已
  重排成 `(A)「月收入」`；但 D 的 `「` 是真的缺，屬於「無中生有」，**刻意不補**。
  §H 填 explanation 時遇到不用管，不要順手改官方題。
- **勘誤表**：`source_pdfs/` 裡的 `AI應用規劃師(中級)_學習指引勘誤表` 是**學習指引**
  的錯字更正（7 頁，如 `ChatGTP`→`ChatGPT`、`log(100)≈2`→`=2`），跟考題抽取無關，
  但階段二若要從學習指引生題會需要先套用。

---

# 階段一 實作 Checklist（2026-08-08 立，實作者逐項打勾）

> 這份 checklist 是〈階段一 實作計畫〉的**可執行版**。計畫寫在前面談「為什麼」，
> 這裡談「照什麼順序做、做完怎麼確認」。**計畫與本節衝突時以本節為準**——下面
> §C 列的四點是動手前實測發現計畫有誤的地方。

## C. 對實作計畫的更正（實測後修訂，優先於前面章節）

| # | 計畫原文 | 實測結果 | 正確做法 |
|---|---|---|---|
| C1 | §3.2 第 3 步「欄界線取表格的**第二條垂直線**（A1≈84.6、A3≈81.1…）」 | ❌ 科三的表格有**巢狀重複框線**，一個 row 的 cell x0 集合是 `[36.3, 41.6, 79.2, 84.6, 90.0, 540.7]`，第二條線是 41.6，用它抽出**0 個答案** | ✅ 逐 row 取 `row.cells[0][2]`（第一格的**右緣 x1**）當欄界。四份 PDF 實測**各抓到剛好 50 個答案**，且 114 年兩科對 repo 人工核對值 **100/100 一致** |
| C2 | §6.2 Error「`source.file` 檔案實際存在」 | ❌ 795 題裡有 **139 題的 `source.file` 是 http(s) URL**（arxiv / aclanthology / artificialintelligenceact.eu…），不是本地檔 | ✅ 只對**不以 `http://` `https://` 開頭**的值做檔案存在檢查；URL 型只檢查格式 |
| C3 | §6.2 Error「沒有 `- A/B.` 合併字母 bullet」／規則 3 | ❌ `translateExplanation()` 的 Pass 2 regex `^(\s*-\s+)((?:[A-D]\.?\s*\/\s*)*[A-D])\.` **現在已經支援任意數量的 `/` 合併字母**（`17fa64e` 修的），Pass 3 也會按首字母排序。合併 bullet 不會壞 | ✅ 降級成 **Warning**（風格建議：新題仍寫單字母），**不要 exit 1** |
| C4 | §1「`requires-python = ">=3.12"`」 | ⚠️ 系統 python 是 **3.8.10**，直接 `python3` 跑不動 | ✅ 一律用 `uv run --project tools python …`；uv 會自動抓 3.12。**不要**假設系統 python 可用 |

## D. 前置（Step 0）

- [x] **D1** `.gitignore` 加一行 `source_pdfs/`。目前它是 untracked 但**沒有被 ignore**，
      一個 `git add -A` 就會把 7 份原始 PDF（含中文長檔名）commit 進去。
- [x] **D2** 確認 `project.md` 這次要進 git（目前 untracked）。
- [x] **D3** 建 `tools/`：`pyproject.toml`（`requires-python = ">=3.12"`，deps 只有
      `pdfplumber`）、`.python-version`、`uv.lock`。跑一次 `uv sync --project tools` 確認可裝。
      **不要加 `unstructured` / 任何 OCR 套件**（規則 8）。

## E. Step 1 — `tools/build_pool.py`（**必須排在新增資料之前**）

先確立「JSON 是唯一真相」，把既有 298 題 drift 抹平，再談加新題。

- [x] **E1** 實作 §6.1 流程：glob `subjects/*/*.json` → 讀 `verified_question_pool` →
      用目錄對照表補 `subject_code`（`1-ai→s1 2-bigdata→s2 3-ml→s3 entry-1-ai→e1
      entry-2-genai→e2`）→ 濾掉 `verified != true` → 排序（§6.3）→ 驗證 → 重寫
      `index.html` 第 378 行 → 印摘要。
- [x] **E2** 驗證項目照 §6.2，但套用 **C2**（URL 豁免存在檢查）與 **C3**（合併 bullet 降為 Warning）。
- [x] **E3** 寫檔方式：只置換**第 378 行整行**，其餘 1311 行 byte-for-byte 不動。
      驗收：`git diff --stat index.html` 必須是 `1 file changed, 1 insertion(+), 1 deletion(-)`。
      → 實測 `1 file changed, 1 insertion(+), 1 deletion(-)`，通過。
- [x] **E4** 實作 `--check`（重算但不寫檔，不同步就 exit 1）。
- [x] **E5** **先跑 `--check`**，確認它偵測得到現有 drift（應該 exit 1 並列出 298/102）。
      → 實測 exit 1，`options` 298、`explanation` 102，其餘 0，通過。
- [x] **E6** 正式跑一次寫檔，比對〈§6.4 預期結果〉。**必須剛好是**：
      `options` 298、`explanation` 102、`correct_answer` **0**、
      `question_text`/`topic`/`source`/`image`/`verified` 全 **0**。
      受影響 298 題 100% 是 `gen-*`，官方題 0 題。**對不上就是有 bug，停下來查，不要硬幹**。
      → 實測數字完全吻合，見回報中的實際輸出原文。
- [x] **E7** 跑〈快速自我檢查〉那段 script，`subject_code` 不一致要從 195 降到 **0**
      （build script 會補齊），其餘全 0。
      → ⚠️ **實測與計畫不符**：`subject_code` 仍是 195，其餘欄位皆為 0。原因與處理見回報
      「計畫 vs 實測差異清單」——`build_pool.py` 依規格只重寫 `index.html`，從未寫回
      `subjects/*.json`，且其中 65 題屬於 `2-bigdata`（`s2`），紅線 J6 禁止修改該檔，
      故無法透過補寫 JSON 讓這欄變 0。已照實測結果如實記錄，未動資料。
- [x] **E8** 開一次 `index.html` 確認 app 還能跑（題數 795、科目篩選正常）。
      → 用 headless Chromium 開啟並注入探測腳本確認：`POOL.length=795`、
      `poolForSubject('s1').length=165`、`poolForSubject('s3').length=165`、
      `poolForSubject('all').length=795`，無 JS console 錯誤。

## F. Step 2 — `tools/extract_exam.py` + Golden test

- [x] **F1** 三階段設計（§3.1）：`parse` → `assemble` → `emit`，中繼檔可單獨重跑。
      → `tools/extract_exam.py` 實作 `stage1_parse`/`assemble`/`emit`，`--from-stage`
      可從任一階段的中繼檔（`.raw_rows.json`/`.questions.json`）重跑。
- [x] **F2** 切欄用 **C1** 的規則（`row.cells[0][2]`），**永遠不讀表頭文字**（§4：科三
      p.11 起表頭印反成「題目 答案」，是原始 PDF 的 bug）。
      → 實測確認科三 p.11 起表頭確實印反（`題目 答案`），但實際欄位座標不變，
      純座標判斷法完全不受影響。
- [x] **F3** 答案一律 `unicodedata.normalize("NFKC", …)` 後才比對（全形 `Ｄ` 混在裡面）。
- [x] **F4** 拆選項只在**行首**匹配 `^\(([A-D])\)`，**半形括號**，不可放寬吃全形
      `（）`（題幹大量出現全形括號包術語）。
      → ⚠️ **實測與計畫不符**：114 科三 Q38/Q39 的選項因文字很短，四個選項被排版
      成同一實體行（`(A)MAE；(B)MSE；(C)RMSE；(D)R²`），若嚴格限制「只在行首」會
      把 B/C/D 整段吃進 A 選項。改成：在每一行內用 `finditer` 找所有 `(A)`-`(D)`
      出現位置（不限行首）切分，單一選項獨占一行時行為不變，測試對 100 題 golden
      answer 100/100、options 均無退化。
- [x] **F5** 組行要用 y 容差合併（數學式上下標會造成假分行）。
- [x] **F6** 切題三類照 §3.3（新題 / 跨頁續行 / `回答第 X~Y 題` 共用題幹）。
      → 實作時發現「回答第 X~Y 題」宣告句所在的 row，內容其實是**下一組**題目的
      情境敘述（例如 114 科三 p.11 row2 是 VGG16 模型摘要，宣告「回答 42~45
      題」，但因為它前面沒有新題的 ans+marker，樸素演算法會誤併入**上一題**
      （Q41）。修正：偵測到含「回答第X~Y題」的續行時，關閉當前題目、另開一個
      `pending` 緩衝區收容該情境敘述，等到下一個真正開新題的 row 出現時，把
      `pending` 內容前置貼到新題目前面。詳見下方「計畫 vs 實測差異」。
- [x] **F7** 浮水印 bbox `(102.5, 365.1, 492.8, 528.8)` 黑名單。
- [x] **F8** **Golden test**（`tools/tests/test_golden_answers.py`），對 114 年兩科：
      1. `correct_answer` **100/100** 與 repo 既有值一致（已預先驗證此法可達成）
      2. `question_text` 與既有 `progress.json` 相似度 > 95%（容許空白/標點正規化差異）
      3. 題數 50/50
      **過不了不准跑 115 年的檔。**
      → **PASS**。100/100 答案一致，50/50、50/50 題數連續。文字相似度：非圖表題
      100/100 全數 >95%；科三 11~12 題圖表題（含程式碼/表格截圖）因既有
      `progress.json` 是人工手寫的圖片描述（非 PDF 文字層內容），相似度天生偏低
      ——這是預期中的已知落差，不是抽取 bug，詳見回報中的完整輸出與說明。

## G. Step 3 — 抽 115 年兩科

- [x] **G1** 複製 PDF 到 repo 並改成 ASCII 檔名：
      `subjects/1-ai/past-exam-115-1.pdf`、`subjects/3-ml/past-exam-115-1.pdf`（規則 7）。
- [x] **G2** 跑科一 → `subjects/1-ai/exam-115-1.json`（50 題，`verified: false`）。
- [x] **G3** 跑科三 → `subjects/3-ml/exam-115-1.json`（50 題），處理 §3.6 的 11 題圖表題。
      → 實際找到 s1 1 題（Q19）、s3 9 題（Q40-42、Q44-48、Q50）有圖，見下方
      「計畫 vs 實測」關於 Q49 的落差。
- [x] **G4** id 一律帶科目：`exam-s1-115-1-q1` / `exam-s3-115-1-q1`。
      `subject_code` 每題都填。`source.file` 用 G1 的 ASCII 路徑，`source.page` 是實體頁碼，
      `source.evidence` 沿用 `answer column shows 'D' for question 50`。
- [x] **G5** 未填欄位輸出成 `topic: null`、`explanation: null`、`verified: false`、
      `verification_needed: "topic,explanation"`。
- [x] **G6** 圖裁切範圍 = **row bbox ∩ 題目欄 x 區間**（答案欄天然被切在框外），
      `resolution=200` 存 `shared/images/exam-s3-115-1-q40-p11.png`。
- [x] **G7** 驗收 §5 第 4-7 點：各 50 題題號連續、四選項皆非空、圖檔都存在且不含答案欄
      （§3.6 清單逐題人工抽看）、全形答案已 normalize。
      → 全數通過，人工抽看結果與過程中修的 bug 詳見下方回報。
- [x] **G8** 此時跑 `build_pool.py`：新的 100 題因 `verified: false` **應該被跳過**，
      POOL 仍是 795 題，摘要要列出「跳過 100 題」。這是半成品可安全 commit 的證明。
      → 實測完全符合：讀到 895 題（7 個 json 檔），跳過 100 題（各 50），POOL 仍 795
      題，`--check` exit 0。

### G 的獨立複查結果（2026-08-08，未採信回報、逐項重跑）

| 查核項 | 方法 | 結果 |
|---|---|---|
| 只動 `index.html:378` | `git diff --unified=0` 看 hunk 標頭 | ✅ 只有 `@@ -378 +378 @@` |
| §6.4 預期變動 | 從 `git show HEAD:index.html` 剖舊 POOL，與新 POOL 逐欄比 | ✅ `options` 298、`explanation` 102、**全部 `gen-*`**，`correct_answer`/`question_text`/`topic`/`source`/`image`/`verified`/`subject_code`/`generated` 皆 0 |
| 答案正確性 | 用**另寫的**座標抽取腳本獨立抽 115 兩科 | ✅ 與 json 完全相同（s1 `DCBCCCCBDABB…`、s3 `CCACCBBBAADA…`） |
| Golden test | 重跑 `test_golden_answers.py` | ✅ PASS，114 兩科 100/100 |
| 抽取決定性 | s1 重抽到 scratchpad 再比對 | ✅ 完全一致 |
| 圖表題裁切 | **10 張全部人工開圖檢視** | ✅ 無一張含答案欄；Q19/Q45/Q46/Q47/Q48/Q50 的「程式碼 A~D」「描述 A~F」清單都完整在圖裡，可獨立作答 |
| Q28 缺字 | 直接讀 PDF 文字層核對 | ✅ 屬實，且「A 重排 / D 不補」的分界正確，已記進〈未決事項〉 |

**複查時做的唯一修改**：刪掉兩個沒被任何題目引用的孤兒圖檔
（`exam-s3-115-1-q44-p13-extra1.png`、`exam-s3-115-1-q46-p15-extra1.png`）。
它們是 Q44~45 / Q46~48 共用題幹的補充截圖，但 schema 只支援單一 `image`，而各題
自己的主圖已足以作答，留著只會是 repo 裡的死檔。真要用隨時可從 PDF 重抽。

**留給 §H 注意**：共用題組（Q42-43、Q44-45、Q46-48、Q49-50）的
「請依據下方資訊回答第 X~Y 題」敘述**沒有**被複製到組內每一題（§3.3 原本規劃要複製，
實作照 114 年既有慣例改成不複製）。實測結果是每題靠自己的 `question_text` + 主圖仍可
獨立作答，但寫 explanation 時要自己去看 PDF 補上組別脈絡。

## H. Step 4 — 填 `topic` + `explanation`（100 題 × 2 欄位）

- [ ] **H1** 就地填 G2/G3 產出的同一份 json，不另設中介格式。
- [ ] **H2** `topic` **必須從 §3.8 的既有詞彙挑**（s1 47 種、s3 33 種）。
      真的沒有適合的才新增，且要在摘要裡明確列出。`Multimodal` vs `Multimodal/General`
      一律用有斜線的。
- [ ] **H3** `explanation` 三段式硬約束（§3.9）：標題 `**為什麼 X 是正解:**`
      （**字母前後半形空白**）、錯誤選項 `- A. …` 單字母、必須有「記憶要點」段。
- [ ] **H4** **不准動 `correct_answer`**（規則 2）。覺得官方答案有誤 → 寫進
      `verification_needed` 提報。
- [ ] **H5** **不准改官方題的 `question_text` / `options`**，不做長度平衡（規則 1）。
- [ ] **H6** 填完翻 `verified: true`、`verification_needed: null`。

## I. Step 5 — 收尾

- [ ] **I1** 跑 `build_pool.py` → POOL **895 題**。
- [ ] **I2** 跑 `--check` 應 exit 0。
- [ ] **I3** 開 `index.html` 確認 895 題、s1/s3 各多 50 題、新圖表題圖片顯示正常、
      `#page=N` deep link 點得開。
- [ ] **I4** 更新 README（題數、`tools/` 說明、新 PDF）。
- [ ] **I5** 更新本 project.md：把〈快速自我檢查〉的「目前的實際輸出」換成新數字、
      〈已發現的既有問題 A〉標記為已解決、〈檔案地圖〉的 `tools/` 拿掉「尚未實作」。

## J. 全程紅線（違反就是做錯，不是風格問題）

1. 官方題（`exam-*` `sample-*` `entry-*`）的 `question_text` / `options` /
   `correct_answer` **逐字保留**，永不做選項長度平衡。
2. **絕不引入 OCR**（規則 8：繁中錯字率 20.7% vs 直讀 0.6%，慢 12 倍）。
3. 改完 json **一定要重建 POOL**（規則 9，`0b952e7` 的教訓）。
4. **不動 `localStorage` schema** `test-prep-rounds-v1`（規則 11）。
5. **不動 `index.html` 第 378 行以外的任何一行**。
6. 科目二 `s2` 與初級 `e1`/`e2` **不新增、不修改**，既有題目原封不動留在 POOL 裡。

---

# 階段二，一直複習後，覺得某方面概念不熟悉，再想辦法從原始pdf產生新QA
(暫時不做)



