@echo off
REM Khởi động "camera relay" (webcam Windows -> WSL qua HTTP MJPEG).
REM   - Bấm đúp file này: chạy với port mặc định 8090
REM   - Hoặc: start_cam_relay.cmd 8091
REM Log ghi vào data\_relay.log. Dừng: (WSL) ./run relay stop
setlocal
set PORT=%~1
if "%PORT%"=="" set PORT=8090
set VENV_PY=%LOCALAPPDATA%\wincam-venv\Scripts\python.exe
if not exist "%VENV_PY%" (
  echo [LOI] Chua cai moi truong Windows. Chay 1 lan:
  echo       powershell -ExecutionPolicy Bypass -File D:\DOAN-NAB\tools\setup_cam_relay.ps1
  exit /b 1
)
"%VENV_PY%" "D:\DOAN-NAB\scripts\win_camera_relay.py" --port %PORT% > "D:\DOAN-NAB\data\_relay.log" 2>&1
