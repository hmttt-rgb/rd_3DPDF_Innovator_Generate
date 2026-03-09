@echo off
chcp 65001

cd /d %~dp0

python -m uvicorn main:app --host 0.0.0.0 --port %API_PORT%
pause