---
name: github_repos
track: bonus
kind: live_api
provider: GitHub Search API
requires_env: []
inputs: [query, sort_by, language, limit]
outputs: [items, total_found]
side_effect: false
---
# github_repos

Tìm repository công khai trên GitHub. Không bắt buộc API key.

Dùng khi người dùng hỏi về **mã nguồn, thư viện, framework, công cụ open-source**
— "có thư viện nào làm X không", "repo nào phổ biến cho Y". Không dùng cho tin
tức (`lookup`), không dùng cho paper học thuật (`papers`), không dùng để đọc một
URL GitHub cụ thể (`fetch`).

`sort_by` nhận `stars` (mặc định — phổ biến nhất), `updated` (còn được bảo trì),
`forks`, hoặc `relevance` (để GitHub tự xếp theo best-match). `language` lọc theo
ngôn ngữ lập trình, ghép vào truy vấn dưới dạng qualifier `language:`.

Mỗi item trả về `metrics.stars` / `metrics.forks` / `metrics.open_issues` và
`date` là lần push gần nhất, đủ để đánh giá repo còn sống hay đã bỏ hoang.

Giới hạn: không có token thì GitHub cho 60 request/giờ. Tool nhận diện lỗi 403
rate limit và trả về thông báo rõ ràng thay vì raw HTTP error. Đặt `GITHUB_TOKEN`
trong `.env` nếu cần hạn mức cao hơn.
