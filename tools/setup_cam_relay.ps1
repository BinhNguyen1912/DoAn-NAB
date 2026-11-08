# Cài môi trường Windows cho "camera relay" (webcam Windows → WSL qua HTTP MJPEG).
#
# Chạy 1 lần trong PowerShell (KHÔNG cần Admin):
#     powershell -ExecutionPolicy Bypass -File D:\DOAN-NAB\tools\setup_cam_relay.ps1
#
# Vì sao cần: usbipd (USB/IP) có thể kẹt trạng thái "Device busy (exported)" — khi đó webcam
# không vào được WSL. Relay chỉ cần Windows mở webcam và phát MJPEG; WSL đọc như "camera IP".
#
# Script tạo venv riêng ở %LOCALAPPDATA%\wincam-venv (KHÔNG đụng python hệ thống) rồi cài
# opencv-python (~40 MB, tải 1 lần).

$ErrorActionPreference = 'Stop'
$venv = "$env:LOCALAPPDATA\wincam-venv"

function Find-Python {
    $candidates = @(
        "$env:LOCALAPPDATA\uv\python\cpython-3.12.15-windows-x86_64-none\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike '*WindowsApps*') { return $cmd.Source }
    return $null
}

Write-Host "[setup] Tạo venv tại $venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    $py = Find-Python
    if (-not $py) {
        Write-Host "[LOI] Không tìm thấy python trên Windows." -ForegroundColor Red
        Write-Host "      Cài Python 3.11/3.12 từ python.org (nhớ tick 'Add python.exe to PATH') rồi chạy lại."
        exit 1
    }
    Write-Host "[setup] dùng python: $py"
    & $py -m venv $venv
}

Write-Host "[setup] Cài opencv-python (tải ~40 MB, chỉ lần đầu)…"
& "$venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check --upgrade pip
& "$venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check opencv-python

& "$venv\Scripts\python.exe" -c "import cv2; print('[setup] OK — opencv', cv2.__version__)"
Write-Host ""
Write-Host "Xong. Bật camera relay rồi demo:" -ForegroundColor Green
Write-Host "    (WSL)  ./run relay        # bật relay + in URL"
Write-Host "    (WSL)  ./run demoip       # bật relay + demo bám VẬT bằng webcam laptop"
Write-Host "Nếu Windows hiện hộp thoại Firewall lần đầu → bấm Allow."
