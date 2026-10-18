# Giải thích đồ án "Camera AI bám bắt đối tượng" — bản dễ hiểu

> Tài liệu này viết cho người **không biết thuật ngữ AI**. Mọi từ chuyên môn đều được giải thích
> bằng ví dụ đời thường. Số liệu lấy từ chính các lần đo trong repo (có file nguồn ghi kèm).

---

## Mục lục

1. [Đồ án làm ra cái gì (1 phút)](#1-đồ-án-làm-ra-cái-gì-1-phút)
2. [Từ điển thuật ngữ — hiểu bằng ví dụ](#2-từ-điển-thuật-ngữ--hiểu-bằng-ví-dụ)
3. [Những gì đang hoạt động](#3-những-gì-đang-hoạt-động)
4. [Nó hoạt động thế nào — vòng đời một khung hình](#4-nó-hoạt-động-thế-nào--vòng-đời-một-khung-hình)
5. [Thiết bị của bạn: mạnh gì, yếu gì](#5-thiết-bị-của-bạn-mạnh-gì-yếu-gì)
6. [Colab là gì và tại sao phải dùng](#6-colab-là-gì-và-tại-sao-phải-dùng)
7. [Bị gì → cần gì → đã làm gì (nhật ký sửa lỗi)](#7-bị-gì--cần-gì--đã-làm-gì-nhật-ký-sửa-lỗi)
8. [Giới hạn — nói thật để không bị hỏi khó](#8-giới-hạn--nói-thật-để-không-bị-hỏi-khó)
9. [Nếu hội đồng hỏi — trả lời mẫu](#9-nếu-hội-đồng-hỏi--trả-lời-mẫu)
10. [Tự kiểm chứng trong 5 phút](#10-tự-kiểm-chứng-trong-5-phút)
11. [Phụ lục: dùng WSL — vì sao và làm thế nào](#11-phụ-lục-dùng-wsl--vì-sao-và-làm-thế-nào)

---

## 1. Đồ án làm ra cái gì (1 phút)

Bạn mở một cửa sổ camera. Bạn **kéo chuột khoanh một vòng quanh một người/vật** (ví dụ khuôn mặt bạn).
Từ đó trở đi, máy tính **tự tô màu vùng đó** (mặt nạ), **vẽ khung quanh nó** (ô bao), **vẽ đường đi**
của nó theo thời gian (quỹ đạo), và **hiện tốc độ xử lý** lên màn hình. Nếu bạn đổi ý, bấm **`r`**
để chọn đối tượng khác; bấm **`q`** để thoát.

Toàn bộ số liệu (mỗi khung hình xử lý mất bao nhiêu mili-giây, đối tượng có bị mất dấu không, tâm
đối tượng ở đâu) được **ghi ra file CSV** để vẽ biểu đồ cho báo cáo.

Nói cách khác: đồ án biến một **mô hình AI có sẵn** (SAM 2) thành một **ứng dụng camera hoàn chỉnh**
mà người bình thường dùng được — đó chính là phần "của bạn".

---

## 2. Từ điển thuật ngữ — hiểu bằng ví dụ

### Nhóm "AI là gì"

| Thuật ngữ | Nghĩa dễ hiểu |
|---|---|
| **AI / mô hình (model)** | Một chương trình đã được "học" từ hàng triệu ảnh, giờ nhìn ảnh mới và trả lời. Giống một người đã học nghề: không cần học lại mỗi lần làm việc. |
| **SAM 2** (Segment Anything Model 2) | Mô hình của Meta Platforms (Facebook) có khả năng **tách một vùng bất kỳ ra khỏi ảnh** khi bạn chỉ vào. "Segment Anything" = "tách cái gì cũng được". |
| **SAMURAI** | Một bản cải tiến của SAM 2 do nhóm nghiên cứu khác làm, thêm trí nhớ chuyển động để **bám** đối tượng tốt hơn khi nó di chuyển/bị che. |
| **Checkpoint / trọng số (weights)** | "Bộ não đã học" của mô hình, đóng gói thành **một file** (~156 MB). Tải file đó về là dùng được, **không cần huấn luyện**. |
| **Huấn luyện (train)** | Quá trình dạy mô hình từ đầu — tốn hàng nghìn giờ GPU. **Đồ án này KHÔNG huấn luyện**, chỉ dùng mô hình có sẵn (đúng như đề cương cho phép). |
| **Suy luận (inference)** | Lúc mô hình "làm bài": đưa 1 khung hình vào, nhận kết quả ra. Đây là phần tốn thời gian mỗi khung. |
| **GPU / CPU** | **CPU** = bộ xử lý chung, giỏi việc lẻ. **GPU** = bộ xử lý hàng nghìn phép tính song song, giỏi việc AI. Laptop bạn **chỉ có CPU** (không có GPU rời của NVIDIA). |

### Nhóm "kết quả nhìn thấy"

| Thuật ngữ | Nghĩa dễ hiểu |
|---|---|
| **Phân đoạn (segmentation)** | Tô đúng **hình dáng** đối tượng, không phải hình chữ nhật. Như tô màu theo đường viền bàn tay thay vì vẽ ô vuông quanh bàn tay. |
| **Mặt nạ (mask)** | Vùng tô màu đó — một lớp điểm ảnh "thuộc về đối tượng". |
| **Ô bao (bounding box / bbox)** | Hình chữ nhật nhỏ nhất bao trọn đối tượng. Đơn giản hơn mặt nạ nhưng thô hơn. |
| **Quỹ đạo (trajectory)** | Đường nối các vị trí tâm đối tượng qua thời gian — nhìn được nó đã đi đường nào. |
| **Bám bắt (tracking)** | Theo dõi đối tượng qua các khung hình sau khi đã chọn ở khung đầu. |
| **Mất dấu (lost)** | Mô hình không tìm ra đối tượng nữa (bị che, ra khỏi khung). Ứng dụng báo bằng banner đỏ và ghi vào CSV. |
| **HUD** | Lớp chữ/số vẽ đè lên video (FPS, độ trễ, điểm tin cậy) — như đồng hồ tốc độ trên kính xe. |

### Nhóm "tốc độ"

| Thuật ngữ | Nghĩa dễ hiểu |
|---|---|
| **FPS (khung/giây)** | Mỗi giây xử lý được bao nhiêu khung hình. Camera thường 30 FPS; phim 24 FPS. |
| **Độ trễ (latency, ms)** | Một khung mất bao nhiêu mili-giây để xử lý. 1000 ms = 1 giây. |
| **Real-time** | Nhanh như thời gian thực (thường hiểu ≥ 10–30 FPS). **Đồ án không đạt trên laptop** và báo cáo trung thực điều đó (xem ADR-0002). |
| **Headless** | Chạy **không cần màn hình** (dùng trên máy chủ/Colab), xuất file video thay vì mở cửa sổ. |
| **Warmup** | Vài khung đầu chậm bất thường (máy "khởi động" chip đồ hoạ). Đo tốc độ nên bỏ khung đầu. |

### Nhóm "cách làm kỹ thuật"

| Thuật ngữ | Nghĩa dễ hiểu |
|---|---|
| **Prompt** | "Gợi ý" cho mô hình biết bạn muốn tách cái gì. Ở đây prompt là **ô vuông bạn kéo chuột**. |
| **Inference state / memory bank** | Bộ nhớ của mô hình về những gì đã thấy ở các khung trước — giúp nó tiếp tục bám khi đối tượng bị che. Càng nhiều khung thì bộ nhớ càng lớn → xử lý càng chậm (đã đo được). |
| **Kalman filter** | Bộ lọc dự đoán "khung sau đối tượng sẽ ở đâu" dựa trên vận tốc — giúp bám mượt. SAMURAI có sẵn phần này, đồ án **dùng lại, không viết lại**. |
| **Temporal propagation** | Lan truyền kết quả từ khung trước sang khung sau (thay vì làm lại từ đầu mỗi khung). |
| **Streaming per-frame** | Đưa **từng khung một** vào mô hình (như camera trực tiếp), thay vì đưa cả video một lúc. **Đây là đóng góp kỹ thuật chính của đồ án.** |
| **YAML config** | File cấu hình dạng chữ dễ đọc (đổi checkpoint, nguồn camera, bật/tắt ghi video… mà không sửa code). |
| **Test tự động / CI** | Bộ kiểm tra chạy lại toàn bộ chức năng mỗi khi sửa code (repo có 142 test). **CI** là dịch vụ tự chạy bộ test đó trên GitHub sau mỗi lần push. |
| **V4L2 / MJPG** | Hai "tiêu chuẩn" để Linux đọc được webcam. Webcam của bạn **chỉ chịu nhả hình khi ép đúng hai thứ này** (xem mục 7). |
| **Bộ đệm (buffer)** | Camera gửi hình liên tục; nếu phần mềm xử lý chậm, hình cũ **ứ lại trong hàng đợi** → bạn thấy cảnh "đi trước, hình hiện sau". |

---

## 3. Những gì đang hoạt động

Đối chiếu **7 yêu cầu của đề cương** — cái nào làm được, bằng chứng ở đâu:

| # | Yêu cầu đề cương | Trạng thái | Bằng chứng |
|---|---|---|---|
| 1 | Thu nhận video trực tiếp (camera USB/IP) | ✅ Webcam laptop, camera IP qua RTSP, và điện thoại qua HTTP (MJPEG) | `src/video_source.py`, 16 test; đo thật: webcam 640×480 đọc 10 khung @35 ms |
| 2 | Người dùng chọn đối tượng | ✅ Kéo chuột khoanh ô; `r` chọn lại | `src/prompt_selector.py`, 12 test; kiểm thật bằng chuột |
| 3 | Phân đoạn & bám theo mặt nạ | ✅ Mặt nạ tô màu + ô bao cập nhật mỗi khung | `src/tracker_engine.py` (bọc SAM 2 streaming), 5 test; IoU 0.95–0.99 trên video giả lập |
| 4 | Trí nhớ chuyển động + lan truyền thời gian | ✅ Dùng nguyên bản SAMURAI (Kalman + memory bank) — không viết lại | `docs/adr/0001`; đo trên kịch bản bị che 5 khung |
| 5 | Hiện vị trí, vùng phân đoạn, quỹ đạo realtime | ✅ HUD 4 dòng + mặt nạ + ô bao + quỹ đạo; chế độ mượt cho video 19 FPS | `src/visualizer.py` (21 test), `data/charts/*_trajectory.png` |
| 6 | Đánh giá FPS, độ trễ, chất lượng, độ ổn định | ✅ Ghi CSV từng khung + tổng hợp + biểu đồ; có cả **IoU** trên dữ liệu giả lập | `src/metrics_logger.py` (14 test), `scripts/plot_metrics.py`, `data/*_summary.json` |
| 7 | (Sản phẩm chạy được) | ✅ 1 lệnh chạy; có cấu hình YAML; chạy được không màn hình (Colab) | `tools/run_live.py`, `configs/default.yaml`, `notebooks/colab_gpu_evaluation.ipynb` |

**Thêm những thứ đề cương không bắt buộc nhưng có:** chế độ hiển thị mượt (tách luồng), banner cảnh
báo mất dấu, điểm tin cậy, cảnh báo khi chọn vào vùng nền, 142 test tự động, CI, tài liệu đầy đủ.

---

## 4. Nó hoạt động thế nào — vòng đời một khung hình

```
  [1] Webcam trả 1 khung hình (ảnh 640×480)
        │
  [2] Ứng dụng đưa ảnh vào SAM 2  ← có kèm "gợi ý": ô vuông bạn đã kéo (chỉ lần đầu)
        │                         ← các lần sau: mô hình tự dùng bộ nhớ các khung trước
        │
  [3] Mô hình trả về:  mặt nạ (vùng đối tượng)  +  ô bao  +  điểm tin cậy  +  thời gian xử lý
        │
  [4] Ứng dụng vẽ lên ảnh: tô màu mặt nạ, vẽ ô bao, nối quỹ đạo, ghi HUD (FPS/độ trễ/điểm)
        │
  [5] Hiện lên cửa sổ  +  ghi số liệu vào CSV  +  (tuỳ chọn) ghi ra file video
        │
  [6] Lặp lại từ [1] cho khung kế tiếp — cho tới khi bạn bấm q
```

Điểm mấu chốt: **mô hình gốc SAM 2 vốn chỉ chạy "cả video một lúc"** (đọc từ ổ cứng).
Đồ án đã **sửa cách gọi** để nó nhận **từng khung từ camera** và vẫn nhớ các khung trước — đó là phần
"streaming per-frame", và là lý do hệ thống dùng được với webcam trực tiếp.

---

## 5. Thiết bị của bạn: mạnh gì, yếu gì

| Thành phần | Thông tin đo được | Ảnh hưởng |
|---|---|---|
| Laptop | MSI Modern 14 B11MOU, CPU 8 luồng | Đủ chạy, nhưng **không có GPU NVIDIA** |
| Webcam | "HD Webcam" 640×480, 30 FPS | Đọc 1 khung chỉ ~32 ms → **không phải nút cổ chai** |
| Mô hình | SAM 2.1 tiny (bản nhỏ nhất) | Trên CPU: **3–8 giây/khung** (0,15–0,3 FPS) |
| Bộ nhớ mô hình | Tăng dần theo số khung đã thấy | Càng chạy lâu càng chậm (3,4 s → 8,3 s) — xem mục 7 |

### Các mức tối ưu đã thử (đều đo thật)

| Thay đổi | Kết quả | Có dùng? |
|---|---|---|
| Giảm độ phân giải **camera** (640×480 → 320×240) | Nhanh hơn **~10%** | ❌ không đáng (vì mô hình tự thu nhỏ ảnh về 1024×1024) |
| Tăng số **luồng CPU** (4 → 8) | Nhanh hơn **~8%** | ❌ không đáng |
| Giảm **độ phân giải đầu vào của mô hình** (1024 → 512) | Nhanh **5–7 lần** | ✅ **dùng** |
| **Reset bộ nhớ định kỳ** (re-anchor mỗi N khung) | Nhanh thêm ~20–30% | ⚠️ dùng có điều kiện (xem mục 8) |
| **Tách luồng hiển thị** (video 1 luồng, mô hình 1 luồng) | Video **19 FPS** thay vì 2 FPS | ✅ **dùng cho demo** |
| Cắt bớt bộ nhớ mô hình trực tiếp | ❌ lỗi (mô hình cần các khung cũ) | ❌ |
| Đo trên **GPU** (Colab) | **15,28 FPS** | ✅ dùng để làm video + lấy số báo cáo |

**Kết luận về máy bạn:** CPU này là **nút cổ chai tuyệt đối** — mọi mẹo phần mềm chỉ cứu được phần
"cảm giác" (video mượt 19 FPS, mặt nạ cập nhật 2 lần/giây), còn tốc độ thật của mô hình vẫn ~0,2–2 FPS.
Đó là lý do cần Colab (mục 6) để có **số liệu GPU** và **video đẹp** cho báo cáo.

---

## 6. Colab là gì và tại sao phải dùng

### Colab là gì (dễ hiểu)
Google cho **mượn một máy tính có GPU** miễn phí, dùng qua trình duyệt (như Google Docs nhưng là máy
tính). Máy đó có **Tesla T4** — chip đồ hoạ chuyên cho AI. Bạn upload code/video lên, bấm chạy, tải
kết quả về. **Không cần cài gì trên laptop.**

### Vì sao phải dùng (3 lý do, gắn với đồ án)

| Lý do | Giải thích |
|---|---|
| **1. Laptop không đủ nhanh** | CPU: 0,20 FPS (5 047 ms/khung) → video chiếu cho hội đồng sẽ là "slideshow". GPU T4: **15,28 FPS** → video xem được như camera thường. |
| **2. Báo cáo cần số liệu GPU để chứng minh "real-time-capable"** | ADR-0002 (quyết định đã thống nhất với GVHD) ghi rõ: số FPS GPU tham chiếu lấy từ **Colab T4**. Không có số GPU thì câu "hệ thống chạy real-time được trên GPU" chỉ là lời nói. |
| **3. Chứng minh hệ thống chạy được trên máy không màn hình** | Chế độ **headless** (không cửa sổ) chỉ thực sự được kiểm khi chạy trên máy chủ — Colab là máy chủ đó. |

### Colab KHÔNG phải là gì (để bạn không bị hiểu sai)
- ❌ Colab **không** viết code hộ bạn — code chạy trên đó là **repo của bạn** (clone từ GitHub của bạn).
- ❌ Colab **không** thay đổi sản phẩm: demo live vẫn là **webcam trên laptop**.
- ❌ Colab **không** huấn luyện mô hình — chỉ chạy mô hình có sẵn nhanh hơn.

### Colab dùng thế nào trong đồ án này
Mở notebook `notebooks/colab_gpu_evaluation.ipynb` → bật T4 GPU → chạy **1 cell "⚡ CHẠY TẤT CẢ"**.
Nó tự: clone repo → cài đặt → tải checkpoint → tạo/ nhận video → chạy pipeline → in số liệu → đóng gói
`data/colab_gpu_results.zip` để tải về.

### Giới hạn của Colab (phải biết để không mất kết quả)
| Giới hạn | Cách xử lý |
|---|---|
| Phiên bị **xoá sạch** khi đóng tab/hết ~90 phút/hết quota | **Tải file kết quả về máy ngay** (hoặc copy sang Google Drive) |
| Mỗi phiên mới phải **tải lại checkpoint 156 MB** (~5–10 phút) | Chấp nhận; hoặc để checkpoint trên Drive |
| Đôi khi hết quota GPU miễn phí | Đổi tài khoản Google, hoặc đợi; hoặc dùng PC có GPU NVIDIA (cùng lệnh) |

### Có phải chạy lại Colab nhiều lần không?
**Không.** Kết quả (video + CSV + JSON) là **sản phẩm tĩnh**: làm 1 lần, dùng mãi cho báo cáo.
Chỉ chạy lại khi **code thay đổi** (phần xử lý/HUD/số liệu) hoặc **đổi tham số** (video, ô chọn,
độ phân giải). Mỗi lần chạy, script ghi `data/gpu_run_info.json` chứa `git_rev` — so với
`git log -1` là biết số liệu còn đúng hay đã cũ.

---

## 7. Bị gì → cần gì → đã làm gì (nhật ký sửa lỗi)

Đây là phần **rất đáng đưa vào báo cáo** (mục "khó khăn và cách giải quyết"), và cũng chứng minh bạn
hiểu hệ thống chứ không chỉ chạy lệnh.

| Vấn đề gặp | Nguyên nhân thật | Cách xử lý | Kết quả |
|---|---|---|---|
| Demo giật, "di chuyển mãi mới nhích" | ① mô hình 3–8 s/khung; ② **driver camera đệm 4 khung** nên hình hiện là hình cũ | ① giảm độ phân giải model + tách luồng hiển thị; ② ép `BUFFERSIZE = 1` (luôn lấy khung mới nhất) | video 0,3 FPS → **19 FPS** (mặt nạ vẫn 2 lần/giây, có ghi "overlay trễ bao lâu") |
| Độ trễ **tăng dần** khi chạy lâu (3,4 s → 8,3 s) | Bộ nhớ mô hình (memory bank) lớn dần theo số khung | Thêm tuỳ chọn **reset bộ nhớ định kỳ** (`--reanchor-every N`); mặc định tắt | giữ độ trễ ~không tăng; **đánh đổi**: mất trí nhớ dài hạn (đã đo: có thể bám sai khi bị che — nên demo che khuất thì **không** bật) |
| Webcam mở được nhưng **không có hình** trên WSL/Linux | OpenCV chọn sai "backend" (obsensor) và cần định dạng MJPG | Ưu tiên **V4L2**, ép **MJPG 640×480** | đọc 10 khung @35 ms |
| `Qt platform plugin "xcb"` rồi process **abort** | Thiếu 2 thư viện hệ thống để mở cửa sổ | Cài `libice6 libsm6` | cửa sổ mở được (WSLg) |
| Không thể thử GUI trên WSL (không màn hình) | WSL không có display lúc đầu | Bật WSLg + cài 2 lib trên; hoặc dùng webcam qua usbipd | kiểm GUI thật thành công |
| Bấm `r` xong thì **lỗi `TypeError: 'NoneType'...`** | **Tranh chấp giữa 2 luồng**: luồng hiển thị xoá trạng thái mô hình trong khi luồng suy luận đang chạy | Chỉ **một luồng** được đụng vào mô hình; luồng kia chỉ gửi yêu cầu | hết lỗi, `r` hoạt động; có test chống tái phát |
| Thoát bằng **Ctrl+C thì mất số liệu** | Phần ghi CSV nằm sau khối `try` nên bị bỏ qua | Ghi CSV/JSON trong `finally` | Ctrl+C vẫn có file số liệu |
| Chọn ô **vào vùng nền** mà hệ thống vẫn "bám" | SAM 2 là mô hình "tách theo gợi ý": **vẽ đâu tách đó**, kể cả nền | Không thể chặn tuyệt đối → thêm **cảnh báo** khi mặt nạ phủ >60% khung + **điểm tin cậy** trên HUD + banner mất dấu | người dùng tự thấy chọn sai |
| Colab: checkpoint tải về **0 byte** | URL cũ trả lỗi **403** (Meta đổi đường dẫn) | Dùng URL mới + **kiểm tra dung lượng >100 MB**, báo lỗi rõ | hết lỗi |
| Colab: `No module named 'loguru'` | `loguru` là phụ thuộc của **SAMURAI**, không nằm trong gói `sam2` | `pip install loguru` | hết lỗi |
| Colab: `inputs must be a CUDA tensor` | Bước "vá lỗ hổng mặt nạ" của SAM 2 nhận dữ liệu sai thiết bị | Tắt bước đó (mặc định) — đồng thời làm số CPU/GPU **so sánh được** | log sạch |
| Số GPU đầu tiên chỉ 2,63 FPS | ① chưa giảm độ phân giải model; ② khung đầu là "warmup" ~3 s làm sai lệch trung bình | Chạy lại với `--image-size 512 --reanchor-every 10`; bỏ khung đầu khi tính | **15,28 FPS** |

> Ghi chú thêm: **T4 là chip đời Turing** nên không bật được "FlashAttention" (một kỹ thuật tăng tốc
> cần chip Ampere trở lên). Vì vậy **15,28 FPS là cận dưới** — GPU đời mới (A100, RTX 30/40) sẽ nhanh hơn.

---

## 8. Giới hạn — nói thật để không bị hỏi khó

| Giới hạn | Vì sao (trung thực) |
|---|---|
| **Không real-time trên laptop** | CPU không có GPU; mô hình ~3–8 s/khung. Đã đo, đã ghi trong ADR-0002. |
| **Không huấn luyện mô hình** | Đề cương cho phép dùng backbone SAM 2 + SAMURAI; đóng góp là **hệ thống** quanh nó. |
| **Một đối tượng tại một thời điểm** | Thiết kế single-object (ADR-0001); chọn đối tượng khác = bấm `r`. |
| **Không tự bắt lại sau khi mất dấu lâu** | Nằm ngoài phạm vi (spec ghi rõ); cách xử lý: bấm `r` chọn lại. |
| **`--reanchor-every` có thể bám sai khi bị che** | Reset bộ nhớ đúng lúc bị che → chọn lại vào nền (đo được IoU 0,509). Khuyến nghị: demo che khuất thì **không** bật. |
| **Số GPU là cận dưới** | T4 không có FlashAttention (như trên). |

---

## 9. Nếu hội đồng hỏi — trả lời mẫu

**1. "Hệ thống này chạy real-time không?"**
> "Trên laptop CPU thì không ạ — đo thật là 0,20 FPS (5 047 ms/khung) vì máy không có GPU rời; em công bố
> trung thực con số này chứ không nói quá. Trên GPU Tesla T4 (Colab) cùng hệ thống đạt **15,28 FPS**,
> tức kiến trúc **đủ khả năng real-time**; em có bảng so sánh 4 môi trường trong báo cáo."

**2. "Vậy em làm gì, hay chỉ chạy repo của Meta?"**
> "Em dùng SAM 2 + SAMURAI làm backbone theo đúng đề cương, nhưng phần em xây là toàn bộ hệ thống:
> adapt mô hình sang **streaming từng khung** để nhận webcam trực tiếp, module chọn đối tượng bằng
> chuột, HUD + mặt nạ + quỹ đạo tiếng Việt, module đo FPS/độ trễ/độ ổn định, cấu hình YAML, chế độ
> headless cho Colab, chế độ hiển thị mượt, cùng **142 test tự động** và CI. Em có tài liệu
> `docs/team-contribution.md` liệt kê từng phần kèm commit."

**3. "Tại sao dùng Colab? Có phải gian lận không?"**
> "Không ạ. Colab chỉ là **máy có GPU cho mượn**, giống như mượn máy tính mạnh hơn để đo. Code chạy trên
> đó là repo của em. Em dùng nó để lấy **số FPS GPU** và **video minh hoạ**, đúng như ADR-0002 đã thống
> nhất với thầy hướng dẫn. Sản phẩm demo live vẫn chạy trên laptop bằng webcam."

**4. "Sao lúc demo video mượt mà số FPS lại thấp?"**
> "Vì em tách làm 2 luồng: luồng camera hiển thị **19 FPS** cho mắt người xem, còn mô hình suy luận
> **~2 lần/giây** — trên HUD có ghi rõ *'Overlay: … ms trước'* để minh bạch. Đây là kỹ thuật
> decoupling, không phải che giấu số liệu."

**5. "Nếu chọn sai đối tượng thì sao?"**
> "SAM 2 là mô hình 'gợi ý đâu tách đó' nên vẽ vào nền nó vẫn trả mặt nạ — em đã đo: nền 1,2% khung với
> điểm tin cậy 17,8 so với đối tượng thật 1,6% / 22,6. Vì không thể chặn tuyệt đối, em thêm **điểm tin
> cậy trên HUD**, **cảnh báo khi mặt nạ phủ >60% khung**, và **banner MẤT DẤU**; người dùng bấm `r`
> chọn lại."

**6. "Số liệu này em tự đo hay lấy ở đâu?"**
> "Tự đo ạ. Mỗi lần chạy, hệ thống ghi CSV từng khung (ms, điểm tin cậy, tâm, cờ mất dấu) và file tổng
> hợp JSON. Em có 4 bộ số: CPU 1024, CPU 384 + smooth, T4 1024, T4 512 — và biểu đồ trong `data/charts/`.
> Mỗi lần chạy còn ghi `git_rev` để biết số liệu tương ứng commit nào."

**7. "Vì sao độ trễ tăng dần khi chạy lâu?"**
> "Vì SAMURAI lưu bộ nhớ các khung đã thấy để bám khi bị che; bộ nhớ lớn dần nên chi phí tăng — em đo
> được 3,4 s ở khung đầu tăng lên 8,3 s sau 8 khung. Em thêm tuỳ chọn reset định kỳ để giữ độ trễ phẳng,
> và ghi rõ đánh đổi là mất trí nhớ dài hạn."

**8. "Hướng phát triển tiếp?"**
> "① Chạy trên GPU thật để demo real-time; ② đa đối tượng; ③ tối ưu mô hình (ONNX/TensorRT) — nằm ngoài
> phạm vi đồ án theo ADR-0002; ④ tự bắt lại đối tượng sau khi mất dấu lâu."

---

## 10. Tự kiểm chứng trong 5 phút

```bash
# 1) Xem toàn bộ lịch sử làm việc
git log --oneline | head -20
ls docs/task/          # 21 file log theo ngày (Input → Xử lý → Output)

# 2) Chạy bộ test nhanh (không cần mô hình, ~10 giây)
source ~/miniconda3/etc/profile.d/conda.sh && conda activate samurai
python -m pytest -m "not slow"

# 3) Chạy demo webcam (mượt)
bash scripts/demo_webcam.sh

# 4) Xem số liệu + biểu đồ
cat data/smooth_summary.json
python scripts/plot_metrics.py data/smooth_metrics.csv --out data/charts
```

| Muốn xem | Mở file |
|---|---|
| Đóng góp cá nhân vs phần có sẵn | `docs/team-contribution.md` |
| Quyết định kỹ thuật & lý do | `docs/adr/0001`, `docs/adr/0002` |
| Cách chạy Colab | `docs/colab-gpu.md`, `notebooks/colab_gpu_evaluation.ipynb` |
| Cài đặt từ máy mới | `README.md` mục 1 |
| Nhật ký từng phiên làm việc | `docs/task/*.md` |

---

## 11. Phụ lục: dùng WSL — vì sao và làm thế nào

### 11.1. WSL là gì (dễ hiểu)

**WSL** = *Windows Subsystem for Linux* — một "máy Linux thu nhỏ" chạy **bên trong Windows**, không cần
cài máy ảo riêng. Điều quan trọng nhất: **file dùng chung**.

```
Windows thấy:  D:\DOAN-NAB\src\visualizer.py
WSL thấy:      /mnt/d/DOAN-NAB/src/visualizer.py     ← CÙNG MỘT FILE
```

Nên bạn sửa code bằng VS Code trên Windows, chạy bằng Python trong WSL — không cần copy qua lại.

### 11.2. Vì sao đồ án này dùng WSL

| Lý do | Giải thích |
|---|---|
| **Mô hình AI cài trên Linux dễ hơn** | SAM 2/SAMURAI hướng dẫn chính thức cho Linux; PyTorch CPU cài bằng 1 lệnh, không vướng lỗi biên dịch trên Windows |
| **Máy bạn chưa có Python trên Windows** | Thay vì cài thêm Python + hàng GB thư viện cho Windows, dùng luôn môi trường Linux sẵn có |
| **Cửa sổ vẫn hiện trên Windows** | WSL2 có **WSLg** — cửa sổ OpenCV hiện ra như ứng dụng Windows bình thường, chuột dùng được |
| **Chạy được trên máy không màn hình** | Cùng môi trường đó dùng cho Colab/chế độ headless → số liệu so sánh được |

> **WSL lo phần "tính toán"**, Windows lo phần "nhìn và cắm thiết bị". Đó là lý do đồ án chạy trong WSL
> nhưng bạn vẫn thao tác chuột trên cửa sổ Windows.

### 11.3. Cài từ đầu (nếu làm lại trên máy khác)

```powershell
# 1) Trong PowerShell (Admin) trên Windows
wsl --install -d Ubuntu          # cài WSL + Ubuntu, khởi động lại nếu được yêu cầu
```

```bash
# 2) Trong Ubuntu (WSL) — gõ lần lượt
sudo apt update
sudo apt install -y git libice6 libsm6      # 2 thư viện cuối: BẮT BUỘC để mở cửa sổ OpenCV

# 3) Python + môi trường
#    (cài Miniconda theo hướng dẫn miniconda.sh, rồi:)
conda create -n samurai python=3.10 -y
conda activate samurai
cd /mnt/d/DOAN-NAB
pip install -r requirements.txt              # numpy, opencv, pyyaml, pillow, pytest, ruff, matplotlib
pip install torch torchvision                 # bản CPU là đủ

# 4) Mô hình (SAMURAI không nằm trong Git — phải clone)
git clone https://github.com/yangchris11/samurai.git samurai
mkdir -p samurai/sam2/checkpoints
wget -O samurai/sam2/checkpoints/sam2.1_hiera_tiny.pt \
  https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt
pip install -e samurai/sam2
pip install loguru                           # SAMURAI cần riêng gói này

# 5) Kiểm tra
python -c "import torch, cv2, sam2; print('OK')"
python -m pytest -m "not slow"               # ~10 giây, không cần checkpoint
```

### 11.4. Cửa sổ hiện trên Windows thế nào (WSLg)

```bash
echo $DISPLAY          # phải ra :0
ls /mnt/wslg           # phải thấy thư mục (WSLg đang bật)
```
Nếu cửa sổ không hiện: cài `libice6 libsm6` (mục 11.3 bước 2) — thiếu 2 gói này thì OpenCV **abort**
ngay khi mở cửa sổ (đúng lỗi đã gặp, xem bảng 11.7).

### 11.5. Đưa webcam vào WSL (WSL không tự thấy webcam)

WSL là "máy khác" nên **không thấy webcam của laptop**. Cần công cụ **usbipd-win** để "gắn" thiết bị USB
sang WSL:

```powershell
# PowerShell (Admin) trên Windows
winget install -e --id dorssel.usbipd-win
usbipd list                          # tìm dòng "HD Webcam", ghi BUSID (VD 1-8)
usbipd bind --busid 1-8              # làm 1 lần (cần Admin)
usbipd attach --wsl --busid 1-8      # mỗi lần khởi động lại WSL phải chạy lại
```
```bash
# Trong WSL
ls /dev/video*                       # phải thấy /dev/video0
sudo usermod -aG video $USER         # cấp quyền đọc camera (làm 1 lần)
#   → sau đó MỞ TERMINAL MỚI (hoặc `newgrp video`) để quyền có hiệu lực
python tools/check_video_source.py --source 0 --num 10
```

**Trả camera lại cho Windows** (để dùng Teams/Camera app):
```powershell
usbipd detach --busid 1-8
```

### 11.6. Lệnh hay dùng trong WSL

| Việc | Lệnh |
|---|---|
| Vào repo | `cd /mnt/d/DOAN-NAB` |
| Bật môi trường | `source ~/miniconda3/etc/profile.d/conda.sh && conda activate samurai` |
| Demo webcam (mượt, ghi video+số liệu) | `bash scripts/demo_webcam.sh` |
| Chạy thử nhanh 5 khung | `bash scripts/demo_webcam.sh --max-frames 5` |
| Kiểm nguồn camera trước khi chạy | `python tools/check_video_source.py --source 0 --num 10` |
| Test nhanh (không cần mô hình) | `python -m pytest -m "not slow"` |
| Vẽ biểu đồ từ CSV | `python scripts/plot_metrics.py data/smooth_metrics.csv` |
| Tắt hẳn WSL (giải phóng RAM) | (PowerShell) `wsl --shutdown` |

### 11.7. Lỗi WSL đã gặp và cách sửa (đều đã xử lý trong repo)

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` rồi process **Aborted** | Thiếu 2 thư viện hệ thống | `sudo apt install -y libice6 libsm6` |
| 5 dòng `QFontDatabase: Cannot find font directory …cv2/qt/fonts` mỗi lần mở cửa sổ | Bản OpenCV không kèm font | Tạo thư mục đó + copy 1 font TTF (lệnh trong README mục sự cố) |
| `Camera index out of range` / mở được nhưng **không có hình** | OpenCV chọn sai "backend" | Code đã ưu tiên **V4L2** + ép **MJPG 640×480** (tự động) |
| `Permission denied` khi mở `/dev/video0` | User chưa ở nhóm `video` | `sudo usermod -aG video $USER` → mở terminal mới |
| `newgrp: command not found` | Ubuntu tối giản thiếu gói | `sudo apt install -y util-linux-extra`, hoặc chỉ cần mở terminal mới |
| Webcam mất sau khi khởi động lại máy | `usbipd attach` chỉ có hiệu lực trong phiên | Chạy lại `usbipd attach --wsl --busid 1-8` |
| Dữ liệu đang ghi bị mất khi `wsl --shutdown` | Tắt WSL = tắt tiến trình Linux | Bấm `q` trong cửa sổ demo trước khi tắt WSL |
| Chạy `python` báo **command not found** | Chưa `conda activate` | `source ~/miniconda3/etc/profile.d/conda.sh && conda activate samurai` |

### 11.8. WSL vs Windows — cái nào làm gì

| Việc | Làm ở đâu |
|---|---|
| Chạy mô hình AI, xử lý video, ghi số liệu | **WSL** (Linux) |
| Xem cửa sổ demo, kéo chuột chọn đối tượng | **Windows** (cửa sổ WSLg) |
| Sửa code | Cả hai (cùng một file trong `D:\DOAN-NAB`) |
| Cắm/rút webcam, quản lý thiết bị USB | **Windows** (`usbipd`) |
| Chạy Colab | Trình duyệt (không liên quan WSL) |

> 💡 Mẹo: đừng đặt môi trường Python (`venv`/conda) **trong** `/mnt/d/...` vì ổ Windows đọc chậm hơn ổ
> Linux — repo này để môi trường ở `~/miniconda3` (trong home Linux) nên khởi động nhanh.
