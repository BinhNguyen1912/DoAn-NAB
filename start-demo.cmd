@echo off
REM Double-click file nay tren Windows de chay viec trong WSL (khong can go lenh).
REM Mac dinh: demo webcam. Co the doi: start-demo.cmd test | start-demo.cmd help
set CMD=%~1
if "%CMD%"=="" set CMD=demo
echo Dang chay: ./run %CMD%  (cua so video se hien ra; bam q de thoat)
wsl.exe bash -lc "cd /mnt/d/DOAN-NAB && ./run %CMD%"
if errorlevel 1 pause
