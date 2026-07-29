---
name: wiki
track: bonus
kind: live_api
provider: Wikipedia REST + Action API
requires_env: []
inputs: [query, lang, limit]
outputs: [items]
side_effect: false
---
# wiki

Tra định nghĩa / bối cảnh nền của một khái niệm, tổ chức hoặc nhân vật trên
Wikipedia. Không cần API key.

Dùng khi người dùng hỏi **"X là gì"**, "giải thích khái niệm X", "background của
tổ chức X" — tức là kiến thức nền ổn định. Không dùng cho tin tức hoặc sự kiện
mới; những thứ đó thuộc `lookup` với `topic="news"`.

Mặc định tra bản tiếng Việt trước. Nếu `vi.wikipedia` không có bài, tool tự lùi
sang `en.wikipedia` (và ngược lại khi `lang="en"`), nên agent không cần đoán
trước ngôn ngữ nào có dữ liệu. Trang định hướng (disambiguation) bị loại vì
không chứa nội dung thật.
