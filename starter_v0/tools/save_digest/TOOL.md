---
name: save_digest
track: bonus
kind: action
provider: local filesystem
requires_env: []
inputs: [markdown, title, confirmed]
outputs: [status, path, filename]
side_effect: local_file_write
requires_confirmation: true
---
# save_digest

Lưu một digest đã hoàn chỉnh xuống `notes/<ngày-giờ>-<slug>.md`.

Đây là **action tool**: nó ghi ra ngoài cuộc hội thoại. Ranh giới xác nhận giống
`send` — gọi với `confirmed=False` (mặc định) chỉ trả về `status:
"needs_confirmation"` kèm tên file dự kiến và số ký tự, **không ghi gì cả**. Agent
không bao giờ được tự đặt `confirmed=True`; cờ đó ghi nhận sự đồng ý của người
dùng nên phải hỏi qua `clarify` với `response_type="yes_no"` trước.

Chỉ dùng khi người dùng yêu cầu **lưu lại** bản digest. Muốn gửi ra Telegram thì
đó là `send`; muốn tạo markdown từ danh sách item thì đó là `format`.

Guardrail: từ chối markdown rỗng, chặn nội dung trên 100.000 ký tự, và làm sạch
`title` thành slug an toàn nên không thể ghi ra ngoài thư mục `notes/`.
