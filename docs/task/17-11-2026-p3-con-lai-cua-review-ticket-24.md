# 17-11-2026 — Hai P3 còn lại của review độc lập ticket #24 (bảng cấu hình + điều kiện công bố)

## Mục tiêu

Báo cáo review độc lập cho nhánh `fix/mask-age-vos-every-1` (ticket #24) về **sau khi PR #27 đã merge**.
Việc cần làm: đối chiếu 7 phát hiện với cây `main` hiện tại, sửa những gì **còn** mở, không làm lại
việc đã sửa.

## Input

- Báo cáo review: 1 P1 + 4 P2 + 3 P3 (agent `reviewer`, chạy trước khi merge).
- Trạng thái `main` @ `46abf0c` (đã merge PR #27/#28/#29/#30).
- Cây sạch, `./run test` **1327 passed** trước khi sửa.

## Công việc đã thực hiện

### 1. Đối chiếu từng phát hiện với cây sau merge

| Phát hiện | Trạng thái trên `main` | Bằng chứng |
|---|---|---|
| **P1** `DINH_NGHIA_TUOI_MASK` vẫn nói "vos_every=1 ⇒ age_n=0" | **đã sửa** (commit `3cc0248`, trước merge) | `src/live_tracking.py` chuỗi mới "mỗi frame PHÁT ⇒ 1 mẫu …" + test ghim cả hai vế (`tests/test_cau_hinh_hieu_luc.py`) |
| **P2** đường inline không ghi `pre_ms` | **đã sửa** (`3cc0248`) | `_after_vos` ghi `_stats.pre_ms`; artifact `bang_cau_hinh_2026-11-17_every1_metrics.json` có `pre_ms.mean 10,96` (trước: `n = 0`) |
| **P2** vế `pre` của test vô răng | **đã sửa** (`3cc0248`) | engine giả trả `pre_ms = 7,0`, test assert `total == 12,5 + 7,0 + post` và `status["pre_ms"] == 7,0` |
| **P2** docstring gọi sai `_consume_vos` + sai "cùng định nghĩa" | **đã sửa** (`3cc0248`) | docstring nay nói "cùng CÁCH ĐO với `_store_vos`, TRỪ `_measure_drift`" |
| **P2** thiếu log phiên cho ticket #24 | **đã có** | `docs/task/17-11-2026-ticket-24-tuoi-mask-don-luong.md` |
| **P3** test "age ≠ thời gian vòng lặp" không bắt được mutation (ngưỡng 50 ms quá rộng) | **đã sửa** (`3cc0248`) | engine giả `elapsed_ms = 400`, assert `approx(pre + 400 + post, abs = 2)` |
| **P3** `age_n` 59 → 60 do mẫu của frame `start()` | **đã ghi** | `AGENTS.md` §6 (bullet ticket #24, câu cuối) |
| **P3** `docs/bang-cau-hinh.md` không có dòng `vos_every 1` | **CÒN MỞ** → sửa hôm nay | xem mục 2 |
| **P3** chỗ công bố số thiếu `git_rev`/clip/ô chọn | **một phần**: `AGENTS.md` đã đủ; `docs/so-lieu-bao-cao.md` thiếu ⇒ sửa hôm nay | xem mục 2 |

### 2. Sửa hai P3 còn mở

**(a) Bảng cấu hình chuẩn nay tự nêu các cấu hình đã đo ở artifact KHÁC.**

`docs/bang-cau-hinh.md` sinh từ **một** artifact (15-11, `vos_every 2/3/6`), nên dòng `vos_every 1` đo
riêng 17-11 không xuất hiện ⇒ người đọc tưởng "chưa ai đo" rồi đo lại từ đầu, hoặc trích số không nguồn.

- `scripts/bang_cau_hinh.py`: hàm mới `artifact_khac(bang, thu_muc)` quét `data/bang_cau_hinh_*_metrics.json`,
  trả các `cau_hinh` **không** có trong bảng chính (kèm `mask_age_p95`, `age_n`, `so_lan`, tên file,
  `git_rev`). Quét theo **mẫu tên file** chứ không ghi cứng tên (tên có ngày, sẽ chết sau vài tuần).
  Artifact hỏng/đang ghi ⇒ bỏ qua (`OSError`/`ValueError`), không làm chết generator.
- `bang_markdown(..., khac=...)` in thêm mục "**Cấu hình đã đo nhưng KHÔNG nằm trong bảng trên**"
  kèm câu **cấm so trực tiếp** (số của lần chạy khác).
- Cờ mới `--render`: sinh lại `.md` từ artifact **có sẵn**, không chạy worker (trước đây muốn đổi cách
  trình bày bảng phải chạy lại 27 phiên ≈ 5 phút, và lần chạy đó ghi đè artifact đã commit).
- Cờ `--khong-quet` để `--check` so được với bản `.md` cũ chưa có mục phụ.

Sinh lại: `scripts/bang_cau_hinh.py --out data/bang_cau_hinh_2026-11-15_metrics.json --render`
⇒ bảng thêm dòng `| 192 | 1 | 109.9 ± 9.32 | 60 | 3 | bang_cau_hinh_2026-11-17_every1_metrics.json (3cc0248) |`.
`--check` vẫn xanh (quét thư mục là hàm thuần, hai đường sinh ra cùng kết quả).

**(b) `docs/so-lieu-bao-cao.md` nêu điều kiện của con số.**

Dòng "Tuổi dữ liệu ảnh p95 ở `vos_every 1`" trong `REGISTRY` (`scripts/so_lieu_bao_cao.py`) nay ghi
**điều kiện**: `image_size 192`, clip `binh1.mp4`, ô chai `300,275,150,410` (và chỉ nơi đọc:
`meta.clip`/`meta.bbox_xywh` trong artifact) — ô chọn là biến số đã từng làm sai toàn bộ kết luận
trước đây (AGENTS §6), nên số công bố phải nêu ô.

### 3. Test thêm (7 test)

`tests/test_bang_cau_hinh.py`:
- `TestCauHinhDoOCArtifactKhac` (5): liệt kê cấu hình ngoài bảng; **không** lặp cấu hình đã có; artifact
  hỏng không làm chết; bảng nêu rõ câu cấm so sánh; không có artifact khác ⇒ bảng **y hệt** bản cũ.
- `TestRenderTuArtifact` (2): `--render` **không** chạy worker (monkeypatch `_run_once` ⇒ ném lỗi nếu bị
  gọi) và ghi đúng `.md`; thiếu artifact ⇒ mã thoát 2 + thông báo.

## Output / Kết quả

- `./run lint` xanh · `./run test` **1334 passed**, 5 deselected (trước: 1327).
- `scripts/so_lieu_bao_cao.py --check` xanh · `scripts/bang_cau_hinh.py --check` xanh.
- `docs/bang-cau-hinh.md` sinh lại từ artifact 15-11 (không đo lại) + `docs/so-lieu-bao-cao.md` sinh lại.
- Không đổi hành vi runtime: chỉ script báo cáo + tài liệu sinh tự động.

## Vấn đề & cách xử lý

- **Báo cáo review về muộn**: PR #27 đã merge từ trước, nên 5/7 phát hiện đã được sửa trong chính PR đó
  (vòng review đó có kết quả trước khi merge). Cách xử lý: **không** làm lại, chỉ đối chiếu từng dòng
  với cây `main` (bảng ở mục 1) rồi sửa 2 P3 còn mở.
- **Không được sửa tay `docs/bang-cau-hinh.md`** (file sinh tự động) ⇒ phải sửa **generator**; nếu chỉ
  sửa generator thì `.md` đã commit vẫn cũ ⇒ thêm `--render` thay vì chạy lại 27 phiên.

## Next steps

- Chờ kết quả **audit sau merge** (reviewer thứ hai, phạm vi 4 PR hôm nay) — nếu có P0/P1 thì mở PR
  follow-up, không sửa thẳng `main`.
- Hai P3 khác của báo cáo này **không cần hành động**: (i) `post_ms` của đường inline vẫn bị "dụng cụ
  đo làm bẩn" trên frame dump mask — đã có ticket **#26** (đã merge, `dump_ms` tách riêng);
  (ii) `cycle_ms`/`queue_ms` còn chứa dump của lần VOS trước — đã ghi trong log #26 là nợ kỹ thuật.
- Ticket #14 vẫn chờ clip thật (`drift_iou_p05 < 0,30` mà `empty ≈ 0`); ticket #11 chờ clip chai đen.

## Tài liệu tham khảo

- Báo cáo review: `.scratch/rev24.md` (vòng 1, trước merge).
- Log gốc của ticket: `docs/task/17-11-2026-ticket-24-tuoi-mask-don-luong.md`.
- AGENTS §6 (bullet `vos_every = 1`), §9.1 (review độc lập), §7b (1 nhánh/nhiệm vụ).
- Artifact: `data/bang_cau_hinh_2026-11-15_metrics.json`, `data/bang_cau_hinh_2026-11-17_every1_metrics.json`.
