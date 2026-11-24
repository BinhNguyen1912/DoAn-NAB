# Vì sao "lúc đúng lúc sai" — model, máy, hay code? (đo 23-11-2026)

> Câu hỏi: cùng một hệ, cùng một vật, lúc bám đúng lúc bám sai, nhận diện lại cũng "tuỳ lúc" — nguyên
> nhân do **model**, do **máy**, hay do **code**?
>
> Cách trả lời: giữ nguyên clip + GT, **chỉ đổi MỘT thứ mỗi lần** rồi chấm `mIoU mask vs GT`. Clip
> `data/binh1.mp4`, GT `docs/gt/b1` (7 frame có vật), `vos_every 1`, CPU, 333 frame.
> Artifact: `data/fac_{A..G}.csv`, `data/fac_{A..G}_masks/`, `data/miou_*` (xem cách tái lập ở §5).

## 0. Trả lời ngắn

| nghi phạm | có phải nguyên nhân? | bằng chứng (cùng clip, cùng GT) |
|---|---|---|
| **Máy** (CPU yếu, ít thread) | **KHÔNG** — chỉ ảnh hưởng tốc độ | ép **1 thread**: mIoU **0,7794** y hệt 4 chữ số, chậm 1,3× (59,1 s vs 44,7 s) |
| **Model** (SAM 2 tiny @192) | **CÓ, là trần độ chính xác** + phụ thuộc tư thế/che khuất | `image_size` 192 → 320 → 512: **0,7794 → 0,8174 → 0,8326** (thời gian 45 → 99 → 276 s) |
| **Code** (ô chọn + re-ID) | **CÓ, là yếu tố LỚN NHẤT đo được** | đổi **ô chọn**: 0,4639 ↔ **0,7794** ↔ 0,6635 ↔ 0,5182 (**Δ 0,32**); bật **re-ID**: 0,4236 (**Δ −0,36**) |
| **Ngẫu nhiên** (model không tất định) | **KHÔNG** — trên file hệ **tất định** | 3 lần chạy cùng cấu hình: kết quả **giống nhau tới 4 chữ số** (cả `binh1` và `clip_be2`) |

## 1. Phát hiện quan trọng nhất: phần "sai" ở đây là **THIẾU**, không phải **SAI VÙNG**

Chồng GT (xanh) với mask model (đỏ) ở f0 — ảnh `data/tmp_gt/gt_vs_model_0.jpg`:

| frame | GT | model | giao | **model nằm trong GT** | mask NGOÀI GT |
|---|---|---|---|---|---|
| 0 | 50 298 px | 27 640 px | 27 587 | **99,8 %** | 0,19 % |
| 181 | 82 293 px | 65 832 px | 65 807 | **99,96 %** | 0,04 % |

Trung bình 7 frame: **`mask_ngoai_gt_mean = 0,006`** ⇒ **0,6 %** mask của model nằm ngoài GT.
Nghĩa là **model không bám nhầm chỗ nào** trên clip này; nó **không tô phần bị tay che và đầu vòi**
(GT làm bằng ngưỡng màu nên bao cả phần bị che). ⇒ mIoU 0,78 ở đây = "model phủ 78 % silhouette mà
người ta kỳ vọng", **không phải** "model bám sai".

Đối chiếu: khi **thật sự** bám sai (re-ID nhận vào tường/áo/poster), `mask_ngoai_gt` nhảy lên
**43,1 %** (tệ nhất 100 %) — đó mới là "sai vùng". **Hai thứ này khác nhau và phải đọc bằng hai cột
khác nhau** trong artifact (`mIoU` vs `mask_ngoai_gt`).

## 2. Bảng thí nghiệm tách yếu tố (mỗi dòng chỉ đổi MỘT thứ)

| # | đổi gì | mIoU | mask NGOÀI GT | thời gian 333 frame | đọc là |
|---|---|---|---|---|---|
| **A** | *(gốc)* ô `300,275,150,410`, 192, không re-ID | **0,7794** | 0,6 % | 44,7 s | mốc |
| **B** | **ô siết vào vật** `280,180,150,330` | **0,4639** | — | 41,9 s | **ô chọn làm hỏng 0,32** |
| **C** | **`image_size` 320** | **0,8174** | — | 98,6 s (2,2×) | model +0,038 |
| **D** | **`image_size` 512** | **0,8326** | — | 276 s (6,2×) | model +0,053 |
| **E** | **máy**: `OMP_NUM_THREADS=1` | **0,7794** | — | 59,1 s (1,3×) | **máy = 0 ảnh hưởng chất lượng** |
| **F** | ô RỘNG `250,140,260,500` | 0,6635 | — | 42,0 s | ô quá rộng cũng tệ |
| **G** | ô RẤT RỘNG `180,100,420,560` | 0,5182 | — | 42,9 s | càng rộng càng tệ |

Hai điều đọc được:

1. **Ô chọn không theo quy tắc đơn giản.** Siết (B) 0,46 · gốc (A) **0,78** · rộng (F) 0,66 · rất rộng
   (G) 0,52. Không phải "ô càng khít càng tốt" cũng không phải "càng rộng càng tốt" — **không thể
   hướng dẫn người dùng bằng một câu**. Đây là lý do "lúc đúng lúc sai" khi tự kéo chuột: **ô đúng
   là một kỹ năng**, không phải thuộc tính hệ thống.
2. **`image_size` là nút thật của model**: 192 → 512 tăng mIoU **+0,053** nhưng chậm **6,2×**
   (45 → 276 s/333 frame ≈ 1,2 FPS ⇒ **không dùng được cho live**, chỉ dùng để chấm/demo bằng file).

## 3. Diễn giải "lúc đúng lúc sai" trong MỘT clip

Cùng một lần chạy (A), IoU từng frame: `0,55 · 0,78 · 0,81 · 0,83 · (vắng) · 0,80 · 0,85 · 0,84`.
Dao động **0,55 – 0,85** mà **không có lỗi nào**: frame 0 vật nhỏ + bị tay che nhiều (model chỉ thấy
mặt trước) → 0,55; frame 211 vật to, ít che → 0,85. ⇒ **"lúc đúng lúc sai" phần lớn là tư thế/kích
thước/che khuất của vật trong khung**, không phải hệ thống "chập chờn".

Cộng thêm hai yếu tố **do code** đã đo riêng:

- **Bật re-ID**: 0,4236 + mask bịa ở **5/5** frame vật đã cất (33 199–52 056 px). ⇒ re-ID **tự tạo ra**
  cái "lúc sai" mà không clip nào khác có.
- **Cổng đóng băng** (`--lost-after-frames`, mặc định 2): đóng băng thì **không gọi model nữa** ⇒
  khả năng tự bám lại của SAM 2 bị vô hiệu hoá (mở cổng: 0,7794; đóng băng + re-ID: 0,4236).

## 4. Kết luận phân công sửa

| việc | vì sao (số) | làm được gì |
|---|---|---|
| Bỏ re-ID khỏi demo | 0,4236 vs 0,7794; bịa mask 5/5 | **xong** — `./run demoip --no-reid` |
| Mở cổng đóng băng | vật vào lại: bám ngay ở f344 (lan truyền) vs trễ 1 frame + bịa (re-ID) | đổi mặc định `--lost-after-frames` (cần đo thêm trước khi đổi) |
| Hướng dẫn/kiểm ô chọn | ô chọn đổi mIoU **0,32** | UI: cảnh báo khi ô quá khít/quá rộng so với vật — **chưa có ngưỡng**, phải đo trên clip thật |
| Tăng `image_size` khi chấm/demo file | +0,053 ở 512 nhưng 6,2× chậm | chỉ cho artifact/báo cáo, **không** cho live |
| Chấp nhận: phần bị che không tô được | model ⊂ GT (99,8 %), thiếu = phần bị tay che | ghi vào hạn chế; muốn hơn phải đổi model (SAM 2 base/large) — **chưa đo** trên máy này |

## 5. Tái lập

```bash
PY=.venv/bin/python   # hoặc env có torch + sam2
FR=0,30,60,91,121,151,181,211,241,272,302,332
for cfg in "A 300,275,150,410 192" "B 280,180,150,330 192" "C 300,275,150,410 320" \
           "D 300,275,150,410 512" "F 250,140,260,500 192" "G 180,100,420,560 192"; do
  set -- $cfg
  $PY tools/run_live.py --source data/binh1.mp4 --image-size $3 --bbox $2 --max-frames 333 \
      --lost-after-frames 999 --lost-score-threshold -99 \
      --dump-mask-frames $FR --dump-mask-dir data/fac_$1_masks --metrics-csv data/fac_$1.csv
  ./run miou score --gt docs/gt/b1 --pred-dir data/fac_$1_masks --out data/miou_fac_$1.json
done
# "máy": OMP_NUM_THREADS=1 ... (cfg A)
```

## 6. Giới hạn phải nói khi trích

- **n = 7 frame có vật**, **1 lần chạy/cấu hình** cho các nhánh B–G. Xu hướng `image_size` nhất quán
  trên **cả 7 frame** (f0: 0,55→0,77→0,79; f181: 0,80→0,84→0,86) nên đọc được là **xu hướng**, nhưng
  repo **chưa có ngưỡng nhiễu cho mIoU** ⇒ **cấm** nói "cấu hình này tốt hơn" như kết luận thống kê.
- GT `b1` làm bằng **ngưỡng màu HSV + người sửa tay** (`docs/gt/b1/index.json`), nên nó bao cả phần bị
  che — đúng cho "silhouette vật" nhưng **không** phải "phần nhìn thấy". Đây là lý do f0 chỉ 0,55.
- Mọi số ở đây là **CPU, `vos_every 1`, file**. Không suy ra cho webcam (nhịp khác, `vos_every 3`).

## 7. Bảng 2×2 ĐẦY ĐỦ (re-ID × cổng đóng băng) — quyết định 23-11

Ô "cổng đóng" = `--lost-after-frames 2` (mặc định); "cổng mở" = `--lost-after-frames 999
--lost-score-threshold -99`. Cùng clip, cùng GT, cùng `image_size 192`, CPU, `git_dirty_code=false`.

| clip (GT) | **không re-ID** | **không re-ID, cổng mở** | **có re-ID** | **có re-ID, cổng mở** |
|---|---|---|---|---|
| `binh1` (7 frame) | **0,7794** | 0,7794 | **0,4236** | 0,7794 |
| `clip_be2` (6 frame) | **0,8754** | 0,8754 | 0,8577 | **0,5668** |

Ba điều rút ra:

1. **Cờ cổng đóng băng KHÔNG có tác dụng khi không bật re-ID** (0,7794 / 0,8754 ở cả hai cột) —
   vì "đóng băng" nằm **trong `ReIdSession`**, không phải trong vòng lặp pipeline. ⇒ muốn "để model
   tự bám lại" thì chỉ cần **không bật re-ID**, không phải sửa cờ nào.
2. **re-ID không thắng ô nào trong 4 ô.** Tệ nhất: `clip_be2` + cổng mở = **0,5668** (mask tràn ra
   ngoài GT **19,6 %**, tệ nhất 50,9 % ở f352) — vì cổng nhảy vẫn reset engine rồi re-ID đi tìm và
   khoá vào vùng khác.
3. ⇒ **Quyết định: `./run demoip` mặc định TẮT re-ID** (`--no-reid`), bật lại bằng `--reid`.
   Không sửa mặc định của `tools/run_live.py` (artifact cũ vẫn tái lập được).

### Đường lui (backup)

- Tag `demo-ok-23-11` + nhánh `backup/demo-ok-23-11` = trạng thái **trước** quyết định này, mọi số ở
  §1–§6 tái lập được y nguyên.
- Quay lại: `git switch backup/demo-ok-23-11` (hoặc `git switch -c ten-moi demo-ok-23-11`).
- Chạy demo kiểu cũ (bật re-ID) **không cần đổi nhánh**: `./run demoip --reid`.
