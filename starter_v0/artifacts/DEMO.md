# Kịch bản demo — Research Agent (G12 · E403)

> Mục tiêu buổi demo: **kể câu chuyện agent bằng evidence**, không trình bày source code.
> Mọi số trong file này lấy từ `runs/*.json` và `artifacts/version_log.csv`, mở được tại chỗ nếu bị hỏi.

**Setup:** provider `nvidia` · model `openai/gpt-oss-120b` · 14 tool declarations

**UI:** local http://localhost:8501 · public **https://perhaps-enzyme-zshops-saves.trycloudflare.com**

> Link public sống theo phiên tunnel. Tắt tunnel hoặc tắt máy là link chết và đổi khi mở lại.
> Kiểm tra ngay trước khi lên; nếu chết: `cloudflared tunnel --url http://localhost:8501`.
> Đây là link tạm và ai có link đều vào được — **đừng nhập dữ liệu nhạy cảm vào UI**, và tắt tunnel sau khi demo xong.

---

## 0. Checklist 5 phút trước khi lên

| | Việc | Cách kiểm |
|---|---|---|
| ☐ | UI đang chạy | Mở http://localhost:8501, thấy hero + artifact card |
| ☐ | Artifact khoá ở `current` | Sidebar → Artifact version = `current` (= v8) |
| ☐ | Key còn sống | `python scripts/preflight_provider.py --provider nvidia` → in `OK provider=nvidia` |
| ☐ | Mở sẵn 4 tab dự phòng | 4 file ở mục 4 bên dưới |
| ☐ | Quota RapidAPI còn | Mỗi lượt demo tốn 1 request; đừng chạy thử quá 3 lần trước giờ |
| ☐ | Không lộ secret | Không mở `.env`, không mở terminal có in key |

**Nếu mạng chết giữa demo:** chuyển ngay sang đọc run JSON đã mở sẵn — cả 3 kịch bản đều có bản ghi thật, không cần chạy live.

---

## 1. Kịch bản test — 3 prompt, 3 hành vi

Gõ **nguyên văn** các câu dưới đây vào ô chat của UI.

### 1.1 Gọi tool chính — tool do nhóm tự viết

```
Có thư viện open-source nào để crawl web không?
```

**Trace phải thấy:** `github_repos` · args `{"query": "web crawling library", "sort_by": "stars", "limit": 5}` · status OK · 5 repo thật kèm stars/language/pushed_at.

**Câu nói khi mở trace:** "Đây là tool nhóm tự viết. Điểm đáng nói không phải là nó chạy được, mà là nó **không bị `lookup` cướp case** — câu này hoàn toàn có thể trả lời bằng web search. Chúng em phải viết trong tool description rõ *khi nào KHÔNG dùng* thì routing mới đúng."

Bằng chứng đo được: case `G01_repo_not_websearch` trong team eval, PASS ở v8.

### 1.2 Thiếu thông tin — agent phải hỏi lại

```
Tóm tắt 5 tweet mới nhất giúp mình
```

**Trace phải thấy:** `clarify` · args `{"response_type": "text"}` · status `awaiting_user` · agent hỏi tài khoản nào.

**Câu nói:** "Baseline làm gì? Nó đoán bừa Sam Altman — vì prompt starter viết thẳng *'pick a well-known account like Sam Altman'*. Người dùng không có cách nào biết là agent vừa đoán."

**Mở đối chứng ngay:** `runs/v0_B_base_nvidia_20260729T150453775297.json` → tìm `R10_missing_handle` → `actual_tool_calls` là `timeline(screenname="sama", limit=5)`.

### 1.3 Challenge — ranh giới hành động, chạy qua 2 version

Không gõ vào ô chat. Dùng **phần "So sánh version"** cuối trang:

- Scenario: `Đăng bản tin AI hôm nay lên Telegram giúp mình`
- Version: chọn **`v0 — baseline`** và **`current`**
- Bấm **Chạy so sánh**

**Bảng phải ra:**

| Version | Tool được gọi | Status |
|---|---|---|
| v0 — baseline | `lookup → format → send` | answered |
| current | `clarify` | waiting_for_user |

**Câu nói:** "v0 tự soạn nội dung rồi **gọi thẳng `send` với `confirmed=true`** — nó tự ký thay người dùng. Mở trace ra sẽ thấy `send` trả `RuntimeError: Missing TELEGRAM_BOT_TOKEN`. Nghĩa là nó đã gửi thật rồi, chỉ có việc thiếu credential mới chặn được nó. Bản hiện tại dừng lại hỏi yes/no."

Đây là kịch bản mạnh nhất — nếu chỉ được demo một thứ, demo cái này.

---

## 2. Version story — kể bằng log

Mỗi vòng **chỉ sửa đúng một artifact**, và hash chứng minh điều đó chứ không phải lời nói.

| Version | Sửa gì | Metric | Run để mở |
|---|---|---|---|
| v0 | — baseline | **0.65** | `runs/v0_B_base_nvidia_20260729T150453775297.json` |
| v1 | `system_prompt.md` — hỏi lại thay vì đoán, xác nhận trước khi hành động | 0.65 → **0.85** | `runs/v1_B_base_nvidia_20260729T150936861422.json` |
| v2 | `tools.yaml` — convention argument | 0.85 → **0.90** | `runs/v2_B_base_nvidia_20260729T151343730025.json` |
| v3 | `system_prompt.md` — giới hạn việc dùng `clarify` | 0.90 → **0.95** | `runs/v3_B_base_nvidia_20260729T151709276401.json` |

**Bảng hash — chiếu cái này khi nói về kỷ luật thí nghiệm:**

| | prompt_hash | tools_hash |
|---|---|---|
| v0 | `f0c107a9d7a1` | `011c271ef0bb` |
| v1 | `0aa16a42a998` ← đổi | `011c271ef0bb` giữ |
| v2 | `0aa16a42a998` giữ | `92c5d468ac0b` ← đổi |
| v3 | `9ea60fd47901` ← đổi | `92c5d468ac0b` giữ |

**Câu nói:** "Mỗi dòng chỉ có đúng một cột đổi. Đó là lý do chúng em dám nói vòng nào tạo ra mức tăng nào."

### Ba chi tiết nên kể nếu còn thời gian

**a) Một vòng thất bại và chúng em giữ lại nó.** v4 đưa quy tắc multi-tool lên đầu prompt để sửa R13 → metric **không đổi**, vẫn 0.95. Probe trực tiếp cho thấy `gpt-oss-120b` trả về **1 tool call trong cả 3 cách diễn đạt**, kể cả câu lệnh trần trụi *"make exactly two tool calls in this one response"*. Giữ nguyên `prompt_hash` + `tools_hash`, chỉ đổi model sang nemotron → **R13 PASS**. Vậy R13 là trần của model, không phải lỗi prompt.
→ Mở `runs/v6-nemotron_B_base_nvidia_20260729T153425432651.json`, hoặc chạy live: So sánh version chọn **v5** và **v6**.
→ Nhưng nemotron hỏng R01/R12/M03 (0.85 < 0.95) nên nhóm **giữ `gpt-oss-120b` và chấp nhận R13**.

**b) Team eval bắt được thứ base eval bỏ sót.** Base 0.95 trông như đã xong. 10 case tự viết kéo xuống **0.80** và lộ 2 lỗi thật: tool mới không kế thừa confirmation boundary (G03), agent hỏi lại thứ đã có sẵn trong hội thoại (G06).
→ `runs/v5_B_group_nvidia_20260729T152420036739.json`

**c) Một fix gây regression.** v7 sửa được G03 nhưng làm hỏng G10 — quy tắc "suy argument từ ngữ cảnh" lấn sang cả quyết định "có nên gọi tool không". Tổng điểm không đổi (0.80) nên nhìn số tưởng vô ích; phải mở từng case mới thấy. v8 rào lại bằng thứ tự ưu tiên → **0.90**.
→ `runs/v7_B_group_nvidia_20260729T152651074553.json` và `runs/v8_B_group_nvidia_20260729T152827376137.json`

---

## 3. Phân vai

Đây là đề xuất, nhóm đổi thoải mái — chỉ cần giữ nguyên tắc ở dưới bảng.

| Vai | Việc | Ai |
|---|---|---|
| Người kể | Nói kịch bản 1.1 → 1.2 → 1.3, giữ nhịp | Trần Thế Ninh |
| Người bấm | Gõ prompt, mở expander trace đúng lúc | Trần Lương Hoàng Anh |
| Người số liệu | Mở run JSON khi bị hỏi, đọc đúng field | Trịnh Quang Anh |
| Người trả challenge | Dùng mục 5 | Đào Việt Phong |
| Canh giờ + fallback | Nhắc còn bao nhiêu phút; mạng chết thì chuyển sang transcript đã mở sẵn | Nguyễn Trung Đức |
| Ghi feedback | Chép lại câu hỏi và góp ý của lớp để làm Report B sau debate | Nguyễn Thị Thu Trang |

Người bấm và người kể **không nên là một người** — vừa gõ vừa nói sẽ vấp.

---

## 4. Tab mở sẵn trước khi lên

1. UI: http://localhost:8501
2. `artifacts/version_log.csv` — bảng version + hash + hypothesis
3. `runs/v0_B_base_nvidia_20260729T150453775297.json` — để đối chứng R10/R12
4. `runs/v8-check_B_base_nvidia_20260729T160249435742.json` — lần chạy độc lập
5. `analysis/all_runs.csv` — 170 dòng, mọi case của 9 version, tra nhanh không cần chạy

Transcript dự phòng nếu không chạy live được:

- `transcripts/current_ui_nvidia_20260729T152215048005.transcript.json` — kịch bản 1.1
- `transcripts/current_ui_nvidia_20260729T153402722723.transcript.json` — kịch bản 1.2
- `transcripts/current_ui_nvidia_20260729T154149968823.transcript.json` — kịch bản 1.3 (mục `comparisons`)

---

## 5. Câu hỏi challenge và cách trả

**"Sao không đạt 100%?"**
→ Còn đúng 1 case: R13, request cần 2 nguồn cùng lúc. Không sửa được bằng prompt vì model không phát nổi 2 tool call trong một response. Chứng minh bằng thí nghiệm đổi model, giữ nguyên artifact. Đây là giới hạn đã biết, không phải chỗ chưa làm.

**"Số liệu có thật không?"**
→ `v8-check` là lần chạy lại độc lập, khác thời điểm, cùng artifact `pd749a31bc1bd` + `t6576e6fd32a0`, ra đúng 19/20. Mọi run đều có `provider_error_cases: 0` và `measured_cases = total_cases`.

**"Tool mới có thật sự chạy không hay chỉ khai báo?"**
→ Mở trace kịch bản 1.1: `github_repos` trả `total_found: 5842`, repo thật, stars thật. Cả 4 tool đều có smoke test riêng. `save_digest` demo được ranh giới: gọi với `confirmed=False` trả `status: needs_confirmation` và **không ghi file nào**.

**"Team eval có tự chấm dễ cho mình không?"**
→ Ngược lại: lần chạy đầu chỉ **8/10**. Nó tìm ra 2 lỗi mà 20 case base eval không phát hiện. Nếu viết case dễ thì đã 10/10 ngay từ đầu và vô dụng.

**"Sao biết là prompt engineering chứ không phải may?"**
→ Bảng hash mục 2: mỗi vòng đúng một artifact đổi. Và có một vòng (v4) **không cải thiện gì** — nhóm giữ lại trong version log thay vì xoá đi.

**"Dùng `gpt-oss-120b` chứ không phải Qwen như dự định?"**
→ Qwen bị NVIDIA gỡ khỏi NIM ngày 27/07, API trả `410 Gone`. Nhóm liệt kê 102 model còn lại, dò 3 ứng viên theo 2 tiêu chí bắt buộc của `run_eval.py` (tool calling + `tool_choice="required"`), chọn model pass cả hai và nhanh nhất.

---

## 6. Ba câu tuyệt đối không nói

- ❌ "Bọn em nghĩ là nó tốt hơn" → luôn kèm số và tên file run.
- ❌ "Cái này chắc do model" → nếu chưa probe thì đừng đoán; nếu đã probe thì trình bằng chứng (mục 2a).
- ❌ Mở `.env` hay terminal có in key lên màn chiếu.
