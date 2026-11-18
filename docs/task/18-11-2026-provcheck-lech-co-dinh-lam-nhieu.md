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
sau  : 52 artifact: 49 ok · 0 lệch · 3 đã-biết · 0 CHẾT-MỚI
```

Nhãn của từng mục `đã-biết` in kèm **trạng thái gốc**: `ok-da-biet(lech)` cho hai artifact 10-11 (rev còn
sống ở object local), `ok-da-biet(chet)` cho mục rev mất hẳn — hai chuyện khác nhau.

Mọi mục `ok-da-biet` đều in kèm lý do, nên thông tin **không mất**: hai mục 10-11 ghi "CẤM dẫn rev", mục
`drift_2026-11-08` ghi rev thật cần dùng (`ee9f25672d72`). `--nghiem` vẫn chỉ chặn `CHẾT-MỚI` (đúng hợp
đồng cũ, `test_allowlist_khong_lam_do` vẫn xanh).

- **File thay đổi**: `scripts/check_artifact_provenance.py`, `tests/test_check_artifact_provenance.py`,
  log này.
- `./run lint` xanh · `./run test` **1402 passed** (5 deselected).
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

## Bổ sung sau review độc lập (2 P2 + 3 P3)

Reviewer (phiên chỉ-đọc; nó còn cảnh báo worktree đổi nhánh giữa phiên — đúng, mình chuyển sang nhánh
khác sau khi mở PR) kết luận **nội dung merge được**, và bắt:

- **P2-1 (mất thông tin)**: `ok-da-biet` **đè** trạng thái gốc ⇒ dòng tổng kết in "3 **chết**-đã-biết"
  trong khi 2/3 là `lech` (rev **còn sống** ở object local, chỉ không phải tổ tiên của `HEAD`). Nay record
  giữ `goc`, nhãn in `ok-da-biet(lech)` / `ok-da-biet(chet)`, tổng kết đổi thành "**đã-biết**"; docstring
  module + `quet()` + đầu `CHO_PHEP` sửa cho khớp (chúng vẫn nói chỉ áp cho rev "ĐÃ CHẾT").
- **P2-2 (test không có răng)**: `test_rev_lech_MOI_van_la_lech` dùng **rev khác + tên file khác** ⇒
  mutant "khoá chỉ theo rev" vẫn xanh. Nay dùng **cùng rev, khác tên file** (kịch bản thật: nhiều
  artifact dùng chung rev — `bang_cau_hinh_*`, `ab_*`) ⇒ mutant đỏ, đã diễn tập.
- **P2-3 (có từ trước)**: `test_rev_chet_moi_khong_duoc_allowlist` hứa "cùng file" nhưng truyền
  `cho_phep={}` ⇒ nay truyền allowlist **cùng tên file, khác rev**.
- **P3**: thêm cờ **`--nghiem-lech`** (opt-in, **không** đổi mặc định vì `lech` là trạng thái hợp lệ của
  nhánh chưa merge) + cảnh báo số `lech` ra stderr; xoá dòng doc rot `--gioi-han-lui` (cờ đó **không**
  tồn tại trong argparse); log thêm danh sách file + mục review này.

**Diễn tập ngược (5/5 đỏ→xanh, mỗi lần phục hồi)**: (a) khoá allowlist chỉ theo `rev` ⇒
`test_rev_lech_MOI_van_la_lech` đỏ; (b) bỏ `goc` ⇒ `test_rev_lech_trong_allowlist_…` đỏ; (c) in nhãn
**không** kèm `goc` (`nhan = r["trang_thai"]`) ⇒ `test_tong_ket_tach_nhan_goc_lech_va_chet` đỏ; (d) trả
lại `return` sớm ở nhánh `chet` ⇒ `test_nghiem_lech_khong_bi_nuot_khi_co_chet` đỏ (bản cũ nuốt cờ,
exit 0); (e) `_la_nguon_webcam` (PR khác) — xem log `18-11-2026-democheck-…`.

**Đã kiểm, không phải lỗi** (reviewer): mã thoát của `--nghiem` không đổi; không consumer nào khác đọc
`trang_thai`; CI `fetch-depth: 0` + allowlist phủ đúng 2 rev ⇒ hành vi CI trước/sau như nhau; khoá
`(f.name, rev)` không bị nới; `treo` (allowlist còn mục nhưng thiếu artifact) vẫn chỉ cảnh báo.

## Bổ sung sau review vòng 2 (1 P2 + 5 P3)

Reviewer vòng 2 (phiên chỉ-đọc) bắt **đúng một lỗ thật của chính mình**:

- **P2 (test không có răng)**: `test_tong_ket_noi_da_biet_khong_phai_chet_da_biet` truyền allowlist cho
  `quet()` (**kết quả vứt đi**) trong khi `main()` dùng `CHO_PHEP` của module ⇒ record là `lech`, và
  assert `"đã-biết" in out` vẫn xanh nhờ dòng tổng kết **luôn** in literal `"0 đã-biết"`. Hệ quả: mutant
  bỏ `({r['goc']})` ở nhãn in **vẫn xanh cả suite** — đúng chỗ P2-1 cần khoá. Nay test **vá `CHO_PHEP`
  trên module** với 1 `lech` + 1 `chet` và assert chính xác `ok-da-biet(lech)`, `ok-da-biet(chet)`,
  `2 đã-biết`. Diễn tập ngược (c): mutant bỏ `goc` ⇒ **đỏ**.
- **P3-1 (`--nghiem-lech` bị nuốt)**: nhánh `chet` `return 1 if args.nghiem else 0` trả **sớm** ⇒ khi có
  `chet` mà không có `--nghiem` thì cờ lech không bao giờ được xét. Nay **gom mã thoát** một chỗ:
  `return 1 if (chet and args.nghiem) or (lech and args.nghiem_lech) else 0`; có test 1 `chet` + 1 `lech`
  + `--nghiem-lech` ⇒ **1** (bản cũ: 0 — đã diễn tập).
- **P3-2**: comment trong `.github/workflows/checks.yml` vẫn nói allowlist chỉ cho rev "chết" ⇒ sửa thành
  "chết/lệch".
- **P3-3**: docstring đầu file nói "**Ba** trạng thái" nhưng có 4 bullet ⇒ "Ba trạng thái (`ok`/`lech`/
  `chet`) + MỘT nhãn hạ allowlist".
- **P3-4**: `--nghiem-lech` không có trong "Cách dùng" của docstring lẫn `./run help` ⇒ thêm; sửa
  `run:184` ("thuộc cây này" chỉ đúng khi bật cờ — mặc định `lech` **không** chặn).
- **P3-5**: test `test_moi_record_deu_co_khoa_goc` dùng rev bịa `abcdef1` ⇒ chỉ chạm nhánh `chet` và
  assert lỏng. Nay dùng rev **HEAD** + assert đúng map `{hong: chet, ok: ok}`.
- **P3-6**: thiếu test "`lech` **đã allowlist** không làm `--nghiem-lech` đỏ" (nếu không, cờ đỏ vĩnh viễn
  trên `main` — tái hiện đúng lỗi "cảnh báo cố định" mà PR này vừa sửa). Đã thêm.

**Ghi chú commit**: `5c1139d` (record artifact hỏng cũng có `goc` + test `test_moi_record_deu_co_khoa_goc`)
được thêm **giữa phiên review** — reviewer đọc lại vùng đó và xác nhận nội dung đúng, chỉ thiếu phần log
(mục này bổ sung).

**Trạng thái**: `./run lint` xanh · `./run test` **1405 passed** (5 deselected) ·
`provcheck` = `52 artifact: 49 ok · 0 lệch · 3 đã-biết · 0 CHẾT-MỚI` ·
`provcheck --nghiem-lech` trên `main` = **exit 0** (2 mục `lech` đã allowlist không làm đỏ).
