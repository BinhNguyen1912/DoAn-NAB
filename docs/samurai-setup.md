# Cài đặt SAMURAI / SAM 2 cho repo này (navigation note)

Ghi lại cơ chế thật của upstream để agent không phải dò lại (mất ~6 tool call trong phiên
implement 05–08). Hướng dẫn cài đặt đầy đủ từ clone mới: **`README.md` mục 1**.

## Vị trí các thành phần

| Thứ | Đường dẫn | Ghi chú |
|---|---|---|
| Package `sam2` (upstream) | `samurai/sam2/sam2/` — cài `pip install -e samurai/sam2` | `samurai/` **không vendor** trong Git (`.gitignore`), phải clone |
| Checkpoint | `samurai/sam2/checkpoints/sam2.1_hiera_tiny.pt` | tải từ `dl.fbaipublicfiles.com/segment_anything_2/...` |
| Config hydra | `samurai/sam2/sam2/configs/` (có `sam2.1/`, `samurai/`) | upstream, KHÔNG copy vào repo |
| Config của repo | `configs/default.yaml` | checkpoint/source/record/metrics — đọc bởi `src/config.py` |

## Cơ chế `model_cfg` (điểm dễ mất thời gian)

`sam2/__init__.py` tự chạy `initialize_config_module("sam2", version_base="1.2")`, nên hydra
tìm config **trong package đã cài**, không phải trong CWD của repo. Vì vậy:

- `model_cfg: configs/samurai/sam2.1_hiera_t.yaml` trong `configs/default.yaml` là **tên
  hydra**, resolve từ package sam2 — chạy được từ bất kỳ CWD nào (đã kiểm chứng).
- Không tạo `configs/samurai/` trong repo: thư mục đó vô nghĩa với hydra và dễ gây nhầm.
- Muốn đổi backbone: sửa `checkpoint` (đường dẫn thật) trong `configs/default.yaml`; chỉ đổi
  `model_cfg` khi bạn hiểu rõ config name khớp kiến trúc checkpoint (`hiera_t/s/b+/l`).

## Kiểm tra nhanh môi trường

```bash
conda activate samurai
python -c "import sam2; print(sam2.__path__)"          # phải trỏ vào samurai/sam2/sam2
ls samurai/sam2/checkpoints/sam2.1_hiera_tiny.pt       # checkpoint đã tải
python -m pytest -m "not slow"                         # làn nhanh, không cần model
```
