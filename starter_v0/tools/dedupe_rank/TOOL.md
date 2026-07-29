---
name: dedupe_rank
track: bonus
kind: local_formatter
provider: none
requires_env: []
inputs: [items, prefer, max_items]
outputs: [items, removed_duplicates, duplicates]
side_effect: false
---
# dedupe_rank

Gộp item thu được từ **nhiều nguồn khác nhau** thành một danh sách duy nhất: khử
trùng lặp rồi xếp hạng. Chạy cục bộ, không gọi API, không tốn quota.

Chỉ dùng khi đã có item từ **ít nhất 2 tool khác nhau** (ví dụ `lookup` +
`social_search`, hoặc `lookup` + `hn_search`). Không dùng khi mới gọi một tool —
lúc đó danh sách chưa có gì để gộp. Đây không phải tool trình bày; muốn ra
markdown thì gọi `format` sau.

Khử trùng lặp theo 3 tầng:

1. URL sau khi chuẩn hóa (bỏ `utm_*`, `fbclid`, `gclid`, bỏ `/` cuối, hạ `www.`);
2. tiêu đề trùng khít sau khi bỏ dấu câu;
3. tiêu đề tương tự — Jaccard trên tập từ nội dung ≥ 0.7, bắt trường hợp cùng
   một tin nhưng mỗi báo giật tít khác nhau.

Xếp hạng theo `prefer="authority"` (mặc định — ưu tiên nguồn gốc như arxiv.org,
openai.com, anthropic.com) hoặc `prefer="recency"` (ưu tiên `date` mới nhất).
Số nguồn cùng đưa tin được giữ lại ở `corroborating_sources` — tin được nhiều
nguồn xác nhận xếp cao hơn.
