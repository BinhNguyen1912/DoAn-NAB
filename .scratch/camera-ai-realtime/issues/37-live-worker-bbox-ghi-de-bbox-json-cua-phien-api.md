# `live_worker --bbox` có thể cướp `bbox.json` của một phiên API đang chờ chọn ô

**Type:** bug (P3, review độc lập vòng 3 ticket #36)
**Status:** needs-triage

## Vấn đề

`tools/live_worker.py` ghi `<out-dir>/bbox.json` khi có `--bbox`, **không kiểm** `<out-dir>` có phiên
API đang chạy (`pid`/`status.json` ở trạng thái `running`/`loading`/`waiting_selection`). Chạy CLI với
`--out-dir` của một phiên web đang chờ chọn ô ⇒ ghi đè ô của phiên đó: phiên web bắt đầu bám **ô của
người chạy CLI**, không cảnh báo.

Đường API thì đã tự bảo vệ (`WorkerFrameSource._prepare_dir` xoá `bbox.json` trong `_OWNED_FILES` lúc
bắt đầu phiên), nên đây là ca "operator chạy CLI vào đúng thư mục live" — hiếm nhưng im lặng.

## Hướng sửa

- Nếu `<out-dir>/<PID_NAME>` trỏ tới tiến trình còn sống **hoặc** `status.json` ở
  `running`/`loading`/`waiting_selection` ⇒ `parser.error` kèm gợi ý `--out-dir` riêng.
- Test: dựng `out_dir` có `status.json` `running` + pid sống ⇒ `--bbox ...` ⇒ mã 2; trạng thái `done`
  (pid chết) ⇒ cho qua.

## Vì sao không sửa trong ticket #36

Ticket #36 là "dump mask mang tên sai frame"; việc này là "CLI chiếm thư mục của phiên API" — cùng file
nhưng khác lớp lỗi, và bản sửa cần bàn về cách nhận biết phiên sống (đã có `_is_our_live_worker` trong
`src/api/adapters/worker_source.py`, nhưng CLI không được import module API).
