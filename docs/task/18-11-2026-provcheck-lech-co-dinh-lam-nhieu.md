# 18-11-2026 — `provcheck`: hai dòng "lệch" cố định đang che mất "lệch" mới

## Mục tiêu

`./run provcheck` in ra **`2 lệch`** ở mọi lần chạy. Kiểm ra thì đó là hai artifact 10-11
(`empty_window_2026-11-10`, `live_web_relay_2026-11-10`) có `git_rev` **chỉ tồn tại ở object local**
(nhánh bị rebase trước khi push) — chúng **đã** nằm trong allowlist `CHO_PHEP` kèm lý do "CẤM dẫn rev",
nhưng allowlist chỉ hạ được trạng thái `chet`, **không** hạ `lech`. Hệ quả: cổng kiểm kêu **cố định**,
nên một `lech` **mới** (artifact đo trên cây không phải tổ tiên của `main`) không còn nổi bật.

## Input

- `scripts/check_artifact_provenance.py` (`quet()`, `CHO_PHEP`, ba trạng thái `chet`/`lech`/`ok-da-biet`)
- `tests/test_check_artifact_provenance.py`
- Hai artifact: `data/empty_window_2026-11-10_metrics.json` (`eb008e3`),
  `data/live_web_relay_2026-11-10_metrics.json` (`da1d671`) — `git merge-base --is-ancestor` trả **1**
  (không phải tổ tiên của `main`), rev vẫn `cat-file -e` được trên máy này.

## Công việc đã thực hiện

1. TDD: 2 test mới **trước** —
   `test_rev_lech_trong_allowlist_duoc_ha_xuong_da_biet` (đỏ: trạng thái vẫn `lech`) và
   `test_rev_lech_MOI_van_la_lech` (allowlist không được nuốt `lech` của artifact khác).
2. `quet()`: hạ allowlist cho **cả** `chet` và `lech` (`if trang_thai in ("chet", "lech") and
   (f.name, rev) in cho_phep`), kèm comment giải thích vì sao.

## Output / Kết quả

```
trước: 52 artifact: 49 ok · 2 lệch · 1 chết-đã-biết · 0 CHẾT-MỚI
sau  : 52 artifact: 49 ok · 0 lệch · 3 chết-đã-biết · 0 CHẾT-MỚI
```

Ba mục `ok-da-biet` đều in kèm lý do (`CẤM dẫn rev`), nên thông tin **không mất** — chỉ là không còn
tính vào dòng "lệch". `--nghiem` vẫn chỉ chặn `CHẾT-MỚI` (đúng hợp đồng cũ, `test_allowlist_khong_lam_do`
vẫn xanh).

- `./run lint` xanh · `./run test` **1392 passed** (5 deselected).
- **Diễn tập ngược**: chỉ hạ `chet` (bản cũ) ⇒ test mới **đỏ**; phục hồi ⇒ xanh.

## Vấn đề & cách xử lý

- **Không** xoá hai artifact khỏi `CHO_PHEP` và **không** sửa `git_rev` của chúng: số đo 10-11 là thật
  (relay camera thật, không sinh lại được nếu không có camera đúng thời điểm), chỉ là rev không truy
  được về `main` — đúng thứ allowlist sinh ra để ghi nhận.
- **Không** sinh lại `empty_window_2026-11-10` trên `main`: nó là bản ghi của một lần đo cụ thể
  (`--expect-lost binh2`/`--expect-keep binh1`, 900 frame/clip); đo lại sẽ ra artifact **mới** với số
  khác, không phải "sửa provenance". Nếu cần số mới thì tạo `empty_window_2026-11-18_*` (chưa làm vì
  chưa có câu hỏi nào cần số đó).

## Next steps

- Nếu sau này nhánh bị rebase lần nữa, thêm cặp `(tên_file, rev)` vào `CHO_PHEP` **kèm lý do** — đừng
  sửa `git_rev` trong artifact.

## Tài liệu tham khảo

- `scripts/check_artifact_provenance.py`, `tests/test_check_artifact_provenance.py`
- `AGENTS.md` §6 (artifact phải có `git_rev` truy được; "cổng kiểm kêu cố định" là nhiễu)
