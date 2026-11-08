"""
Các adapter (hạ tầng) của tầng API — hiện thực cụ thể cho `src.api.ports`.

Chức năng: gom 3 hiện thực mặc định để composition root (`main.create_app`) lắp ghép.
Lưu ý  : chỉ composition root được import package này — service/routes KHÔNG được import,
         nếu không sẽ mất khả năng thay thế hạ tầng (vi phạm DIP).
"""

from src.api.adapters.cv2_probe import Cv2VideoProbe
from src.api.adapters.fs_store import FileSystemJobStore
from src.api.adapters.opencv_source import OpenCvFrameSource
from src.api.adapters.subprocess_runner import SubprocessPipelineRunner
from src.api.adapters.worker_source import WorkerFrameSource

__all__ = ["Cv2VideoProbe", "FileSystemJobStore", "OpenCvFrameSource",
           "SubprocessPipelineRunner", "WorkerFrameSource"]
