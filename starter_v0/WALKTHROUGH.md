# Walkthrough — Day 04 Lab (Research Agent Tool Eval)

Ghi chú tiến độ hiện tại + toàn bộ yêu cầu đề bài + rule bắt buộc phải pass + kiến thức nền cần biết để làm đúng, không chỉ làm theo lệnh. Tick vào ô khi xong.

---

## 0. Kiến thức nền — hiểu trước khi làm

### Vòng lặp evidence-driven là gì

Lab này KHÔNG chấm "chatbot trả lời hay". Nó chấm khả năng của nhóm trong việc:

1. Chạy agent thật (gọi tool thật, có thể fail thật vì HTTP 403, rate limit...).
2. Đọc log JSON để tìm bằng chứng agent sai ở đâu (chọn sai tool? sai argument? không hỏi lại khi thiếu info? tự ý làm hành động nhạy cảm?).
3. Đặt **một giả thuyết cụ thể** cho lý do sai.
4. Sửa **đúng một thứ** (prompt hoặc tool declaration) để kiểm chứng giả thuyết.
5. Chạy lại, so sánh metric trước/sau bằng số thật, ghi lại.

Nếu bạn sửa 5 thứ cùng lúc rồi chạy lại thấy tốt hơn, bạn **không biết cái nào thực sự có tác dụng** — đây là lỗi phổ biến nhất, giám khảo sẽ hỏi "sao biết là do thay đổi này".

### Tool declaration cũng là prompt

Model không "hiểu" tool bằng phép màu — nó chỉ thấy `name`, `description`, `parameters` (JSON schema) trong `tools.yaml`. Nếu mô tả mơ hồ (như `clarify` gốc: "Gửi một câu hỏi cho người dùng"), model sẽ đoán mò cách dùng, kể cả khi `system_prompt.md` đã nói đúng. Ví dụ thực tế nhóm đã gặp: thêm rule "luôn confirm trước khi gửi" vào system prompt không đủ — phải sửa cả `tools.yaml` (bắt `response_type` là `required` + giải thích khi nào dùng `yes_no`/`text`/`choice`) mới hết lỗi.

→ Rule thực hành: khi 1 case fail, luôn hỏi "đây là lỗi do agent không biết PHẢI làm gì (system_prompt) hay không biết CÁCH gọi tool đúng (tools.yaml)?"

### Các trục đo (metric) nghĩa là gì

- `tool_routing_accuracy`: agent có **chọn đúng tool** không (bất kể argument đúng hay sai).
- `argument_accuracy`: trong số case routing đúng, **argument có đúng** không (tên account, query, limit, response_type...).
- `case_accuracy`: case pass hoàn toàn (routing đúng **và** argument đúng, hoặc không gọi tool khi không nên gọi).
- `multiturn_accuracy`: riêng các case nhiều lượt (agent có nhớ và carry-over đúng context từ lượt trước không).
- `provider_error_cases`: số case bị lỗi do provider/API (không phải lỗi agent) — **phải bằng 0** thì các số trên mới đáng tin.
- `measured_cases` phải bằng `total_cases` — nếu không, một số case bị bỏ qua và metric bị lệch.

Quan trọng: **PASS ở routing không có nghĩa tool chạy đúng thật sự**. Nhìn ví dụ `R01` trong `v0`: agent gọi đúng tool `timeline` với đúng args, nhưng `tool_results` trả về lỗi `403 Forbidden` (do RapidAPI key/plan). Phải tự đọc `tool_results[*].result` để biết tool có thực sự chạy được không — eval không tự động chấm phần này.

### 6 loại `failure_type` cần phân biệt (dùng khi viết eval_group.json)

| failure_type | Nghĩa | Ví dụ |
|---|---|---|
| `wrong_tool` | Gọi sai tool | Hỏi "tweet của X" nhưng agent gọi `lookup` thay vì `timeline` |
| `wrong_arg_value` | Đúng tool, sai giá trị argument | `limit` sai số, `query` bị thêm chữ thừa |
| `wrong_boundary` | Vi phạm ranh giới xác nhận | Gửi Telegram luôn thay vì hỏi confirm trước |
| `unnecessary_tool` | Gọi tool khi không cần | Câu hỏi meta ("bạn là ai") mà vẫn gọi tool |
| `out_of_scope` | Câu ngoài phạm vi nhưng agent vẫn cố trả lời/gọi tool | Hỏi toán, code — agent phải từ chối, không tool |
| `missing_info` | Thiếu thông tin bắt buộc mà agent không hỏi lại | Không có handle/URL nhưng agent tự đoán |

---

## 1. Yêu cầu đề bài đầy đủ (Scope)

Nhiệm vụ **bắt buộc**:

- [x] Setup chạy được bằng provider thật (đã xong).
- [ ] Agent có **≥5 tool** trong `artifacts/tools.yaml` (hiện có 6 core: `clarify`, `timeline`, `social_search`, `lookup`, `fetch`, `format` — đã đủ, nhưng cần cộng thêm tool mới của nhóm).
- [x] Chạy base eval (`v0` xong).
- [x] Tối ưu **≥3 vòng** sau baseline: `v1`, `v2`, `v3` — đã xong, mỗi vòng phải là cải tiến thật (không copy-paste giống nhau).
- [x] Ghi `artifacts/version_log.csv` — đã điền đủ v0-v3 với hash + metric thật.
- [ ] Viết **≥1 tool mới**, kèm `TOOL.md`, đăng ký `tools/__init__.py` và `tools.yaml`.
- [ ] Tự viết đúng **10 eval case** vào `data/eval_group.json`: 5 single-turn + 5 multi-turn.
- [ ] Nộp run JSON, transcript JSON, report.
- [ ] Có **UI chạy được** (khuyến nghị Streamlit, nhưng framework nào cũng được). UI là core deliverable, **không phải bonus** — starter không có sẵn `app.py`.
- [ ] Hoàn thành `artifacts/REPORT.md`: **Phần A xong trước 16:30**; Phần B hoàn thiện sau demo.

**Điểm bonus**: hoàn thành UI bắt buộc **và** tự viết **>3 tool mới**. UI riêng lẻ hoặc dùng optional tool có sẵn (`send`, `policy`, `papers`, `paper_text`) **không** tính bonus.

**Optional tool có sẵn** (không tính là tool mới của nhóm, nhưng vẫn có thể đổi routing nếu declaration còn trong `tools.yaml`):
- `send`: gửi Telegram, live-send optional.
- `policy`, `papers`, `paper_text`: tải/trích PDF, optional.

---

## 2. Rule bắt buộc phải theo — dễ mất điểm nếu bỏ qua

### 2.1. Rule khi rename tool

Nếu đổi tên bất kỳ tool nào, **phải sync đồng bộ cả 8 file sau**, thiếu 1 file là eval sẽ báo `not declared in tools.yaml` hoặc model/grader nói hai thứ khác nhau:

1. `artifacts/system_prompt.md`
2. `artifacts/tools.yaml`
3. `tools/<tool_name>/TOOL.md`
4. `tools/__init__.py`
5. `data/eval_base.json`
6. `data/eval_research_extension.json`
7. `data/eval_group.json` (nếu case nhóm có nhắc tool đó)
8. `artifacts/REPORT.md` + demo/poster text

Trong fixed eval (`eval_base.json`, `eval_research_extension.json`): **chỉ đổi field tên tool** để sync rename — **không** được sửa query, expected args, hoặc expected behavior.

### 2.2. Rule giới hạn khi tối ưu (Step 2/3)

Trong mỗi vòng tối ưu routing, **chỉ được sửa**:
- `artifacts/system_prompt.md`
- `artifacts/tools.yaml`

**Không** được sửa case trong `data/eval_base.json` (trừ rename theo 2.1). Viết tool mới thì không bị giới hạn này (cần `TOOL.md`, `tool.py`, đăng ký `__init__.py`, thêm `tools.yaml`, rồi smoke-test).

### 2.3. Rule cho `data/eval_group.json`

- Đúng 10 case: 5 single-turn (field `query`) + 5 multi-turn (field `turns`).
- Mỗi case bắt buộc có: `id`, `phase: "B"`, `failure_type` (1 trong 6 loại ở mục 0), `expect` (`tool_calls` hoặc `no_tool`), `metadata.what_it_tests`.
- Multi-turn: phần tử **cuối cùng** trong `turns` phải là user turn đang được chấm.
- 2 case mẫu trong `samples/eval_group.schema.example.json` **không tính** vào 10 case và **không được nộp thay** case của nhóm.

### 2.4. Gate matrix (từ TOOL-SETUP.md) — cái gì bắt buộc quicktest

| Capability | Quicktest bắt buộc? | Ghi chú |
|---|---|---|
| Provider + core API dùng trong base eval | **Có** | Phải pass trước khi chạy eval |
| Tool mới đầu tiên nhóm viết | **Có** | Quicktest bằng gọi tool trực tiếp qua `TOOL_FUNCTIONS`, không qua agent |
| Tool mới thêm để lấy bonus | Khi claim bonus | Cần quicktest + evidence như tool bắt buộc |
| UI | **Có** | Mở được, chạy được luồng demo chính |
| Optional built-in (`policy`/`papers`/`paper_text`/`send`) | Chỉ khi demo/dùng | Fail không chặn core; Telegram creds phải unset trong mọi `run_eval` |
| Extension suite | Không | Chỉ chạy nếu nhóm chọn dùng optional built-in |

Quicktest research tool chỉ **PASS** khi `error is None` và có kết quả đúng kỳ vọng. Telegram dry-run chỉ PASS khi `status == "needs_confirmation"`.

### 2.5. Rule bảo mật — không được vi phạm

- Không commit, chụp màn hình, hoặc đưa `.env`/API key/Telegram token vào bất kỳ đâu (git, report, log, screenshot, transcript, poster).
- Không print raw exception của Telegram API (URL lỗi có thể chứa bot token).
- Không nhập dữ liệu nhạy cảm vào UI đã public qua tunnel.
- Trong mọi `run_eval`, để Telegram credentials **unset** (case Telegram trong base chỉ chấm `clarify(response_type="yes_no")`, không chấm gửi thật).

### 2.6. Rule đọc metric đúng cách

Trước khi tin bất kỳ số nào trong `summary`:
- `provider_error_cases` phải `== 0`.
- `measured_cases` phải `== total_cases`.
- Case có `tool_results` chứa `error` phải **tự đọc thủ công** — PASS routing không đảm bảo tool chạy thành công.

---

## 3. Tiến độ hiện tại của nhóm

- [x] Setup: venv, `pip install -r requirements.txt`, `.env` tạo từ `.env.example`, preflight provider OK.
- [x] Baseline `v0`: `case_accuracy = 0.65`, `tool_routing_accuracy = 0.75`, `argument_accuracy = 0.65`.
- [x] `v1` (sửa `artifacts/system_prompt.md`): bỏ rule "đoán bừa" + "cứ gửi luôn", thêm rule `clarify` khi thiếu info, confirm trước khi gửi, out-of-scope không gọi tool, không nhồi chữ vào `query`. → `case_accuracy = 0.90`, `tool_routing_accuracy = 1.0`.
- [x] `v2` (sửa `artifacts/tools.yaml`): mô tả rõ tool `clarify` (khi nào dùng `yes_no`/`text`/`choice`), bắt `response_type` là `required`. → `case_accuracy = 0.95`.
- [x] `v3` (sửa `artifacts/system_prompt.md`): thử ưu tiên rule confirm-before-send lên trên rule hỏi thiếu info. → vẫn `0.95` — hypothesis chưa đủ mạnh, case `R12_confirm_before_send` vẫn fail.
- [x] `v4` (sửa cả `system_prompt.md` + `tools.yaml`): thêm ví dụ cụ thể (few-shot) đúng tình huống R12 vào system prompt, đồng thời reinforce rule "response_type luôn là yes_no cho request gửi/đăng" ngay trong mô tả tool `clarify`. → **`case_accuracy = 1.0` (20/20 pass)**.
- [x] `artifacts/version_log.csv` đã điền đủ v0–v4 với hash + metric thật.

---

## 4. Còn lại — làm theo thứ tự này

### Bước 1: ~~Thử v4~~ — Đã xong, `case_accuracy = 1.0` (20/20)

Đã fix xong case `R12` bằng cách thêm ví dụ cụ thể (few-shot) vào `system_prompt.md` + reinforce rule ngay trong mô tả tool `clarify` ở `tools.yaml`. Bài học ghi vào `REPORT.md`: rule dạng câu văn xuôi (v3) không đủ mạnh để ghi đè xu hướng mặc định của model; phải kết hợp ví dụ cụ thể + reinforce ở tầng tool declaration mới hiệu quả.

### Bước 2: Viết tool mới (bắt buộc ít nhất 1)

Xem cấu trúc có sẵn ở `tools/timeline/` hoặc `tools/lookup/` để theo đúng convention.

- [ ] Tạo `tools/<ten_tool>/tool.py` (implementation) + `TOOL.md` (mô tả theo format các tool khác).
- [ ] Đăng ký trong `tools/__init__.py` (thêm vào `TOOL_FUNCTIONS`).
- [ ] Thêm declaration (`name`, `description`, `parameters`) vào `artifacts/tools.yaml`.
- [ ] Cập nhật `artifacts/system_prompt.md` nếu cần định hướng routing tới tool mới.
- [ ] Smoke-test **trực tiếp qua `TOOL_FUNCTIONS`** (không qua agent) — xem mẫu lệnh ở `TOOL-SETUP.md` mục "Core smoke test cho tool mới bắt buộc". PASS khi `error is None`.
- [ ] Muốn bonus: làm **>3** tool mới (không tính tool optional có sẵn).

### Bước 3: Viết 10 eval case vào `data/eval_group.json`

File hiện là template trống. Theo đúng rule ở mục 2.3. Nên cover ít nhất 1-2 case liên quan tool mới vừa viết.

```bash
python run_eval.py --provider openrouter --version v3 --suite group --eval-cases data/eval_group.json
```
(dùng version hiện tại; không tính là vòng tối ưu mới trừ khi cố tình sửa prompt/tool để pass case nhóm — nếu có sửa, đặt tên version mới và ghi log như bình thường.)

### Bước 4: Build UI (deliverable bắt buộc, không phải bonus)

- [ ] Thêm `streamlit>=1.30.0` vào `requirements.txt`, `pip install -r requirements.txt` lại.
- [ ] Tạo `app.py` ở `starter_v0/`, **tái sử dụng** `run_model_tool_loop` trong `chat.py` — không viết agent loop riêng.
- [ ] Hiển thị tối thiểu: request/response cuối cùng; trace từng tool (tên, args, round/status, result/error); `transcript`/`run`/`artifact_version` hiện tại; cùng scenario chạy qua nhiều version để so sánh.
- [ ] Không render/log secrets lên UI.
- [ ] Chạy `streamlit run app.py`; PASS khi mở được `http://localhost:8501` không lỗi.

### Bước 5: Chat live — thử tương tác thật

```bash
python chat.py --provider openrouter --version v3
```
Thử tối thiểu 3 turn:
- [ ] 1 request research bình thường.
- [ ] 1 request thiếu thông tin → bổ sung ở lượt sau.
- [ ] 1 request hành động nhạy cảm → kiểm tra agent hỏi lại/xác nhận đúng boundary.

Transcript tự lưu vào `transcripts/*.transcript.json`.

### Bước 6: Deploy để team khác test được

```bash
cloudflared tunnel --url http://localhost:8501
```
- [ ] Lấy URL `trycloudflare.com`, test lại bằng máy/browser khác trước showdown.
- [ ] Không để lộ secrets/API key trong UI public.
- [ ] Paste URL vào `REPORT.md` phần A.
- [ ] Tắt tunnel sau demo.

### Bước 7: Hoàn thiện `artifacts/REPORT.md`

- **Phần A** (xong trước 16:30): 1 trang giới thiệu nhanh — agent có tool gì, làm được gì, câu hỏi mẫu để test, link demo. Đây là tài liệu phụ trợ khi demo, không phải bản nộp cuối.
- **Phần B** (hoàn thiện sau debate/demo): bảng đầy đủ v0–v3 (+v4 nếu có), failure analysis chi tiết (bao gồm case R12 nếu chưa fix), 10 eval case + kết quả group suite, live chat transcript, reflection dựa trên log thật.

### Bước 8: Rehearse demo (trước showdown 16:30)

- [ ] Chọn 3–5 scenario cụ thể, chạy xuyên suốt v0 → version mới nhất để show cải thiện rõ ràng.
- [ ] Chuẩn bị fallback run/transcript nếu mạng chập chờn.
- [ ] Kiểm tra API key, quota, link demo còn sống.
- [ ] Không để lộ secrets trong screenshot/log/poster.

### Bước 9: Áp dụng feedback sau showdown → v3 cuối (checkpoint 17:15–17:35)

Sau khi bị challenge trong showdown, áp dụng feedback thật, chạy version mới, cập nhật report bằng evidence — đừng chỉ sửa report mà không chạy lại eval.

### Bước 10: Submit

Nộp `starter_v0/` gồm:
- `artifacts/system_prompt.md`, `artifacts/tools.yaml`, `artifacts/version_log.csv` (≥v0-v3), `artifacts/REPORT.md`
- `data/eval_group.json` (đúng 10 case)
- `runs/*.json`
- `analysis/*.csv` (nếu có parse run log)
- `transcripts/*.transcript.json`
- implementation tool mới, code UI, dependency tương ứng

**Không nộp**: `.env`, API key, `.venv/`, cache/build output.

Kênh nộp, quy tắc đặt tên file, và deadline cuối theo thông báo giảng viên — xác nhận trước khi zip/gửi link.

---

## 5. Checkpoint timeline (14:00–18:00) — để biết đang trễ/đúng giờ

| Giờ | Checkpoint |
|---|---|
| 14:00–14:15 | Kickoff — chia nhóm, phân vai, mở `starter_v0/` |
| 14:15–14:40 | Setup — môi trường, API key, provider preflight |
| 14:40–15:15 | Baseline v0 — chạy base eval, đọc 1 failed trace, dựng UI local, ghi 4 metric |
| 15:15–15:50 | v1 + Tool — sửa 1 hypothesis, hoàn thiện 1 tool mới, chạy v1, cập nhật version log |
| 15:50–16:05 | Nghỉ |
| 16:05–16:30 | Eval + v2 — hoàn thành 10 team eval case, evidence v2, 3 kịch bản demo, Report A, rehearsal |
| 16:30–17:15 | Showdown — giới thiệu, live test, challenge |
| 17:15–17:35 | v3 + Report B — áp dụng feedback, chạy v3, hoàn thiện report bằng evidence |
| 17:35–17:40 | Final gate — kiểm tra, chuẩn bị nộp `starter_v0/` |
| 17:40–18:00 | Kahoot Recap |

**Lưu ý**: nhóm hiện đã xong tới v3 sớm hơn timeline gốc (timeline gốc dự kiến v1 ở 15:15-15:50, v2 ở 16:05-16:30, v3 ở 17:15-17:35 sau showdown). Việc chạy nhanh không sai, nhưng nhớ: sau showdown feedback thật có thể phát sinh thêm case cần sửa — đừng coi v3 hiện tại là bản cuối cùng tuyệt đối, có thể cần v4/v5 sau khi bị challenge.

---

## 6. Lệnh tham khảo nhanh

```bash
# chạy 1 vòng eval mới
python run_eval.py --provider openrouter --version vN --suite base --eval-cases data/eval_base.json

# chạy eval nhóm tự viết
python run_eval.py --provider openrouter --version v3 --suite group --eval-cases data/eval_group.json

# optional: chạy extension suite (chỉ nếu dùng optional built-in tools)
python run_eval.py --provider openrouter --version v3 --suite extension --eval-cases data/eval_research_extension.json

# parse run JSON thành CSV để phân tích
python scripts/parse_runs.py runs/ --output analysis/base_runs.csv

# chat live
python chat.py --provider openrouter --version v3

# smoke-test tool mới (thay TOOL_NAME/ARG/VALUE)
python -c "from pathlib import Path; from env_loader import load_lab_env; load_lab_env(Path.cwd()); from tools import TOOL_FUNCTIONS as T; r=T['YOUR_TOOL_NAME'](**{'YOUR_ARG':'DEMO_VALUE'}); print({'error':r.get('error') if isinstance(r, dict) else None, 'result_type':type(r).__name__})"

# UI
streamlit run app.py

# deploy tunnel
cloudflared tunnel --url http://localhost:8501
```
