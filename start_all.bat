@echo off
chcp 65001 >nul
echo =========================================================================
echo    基于 LightGBM 与特征归因的股票 Top-K 推荐系统 一键启动器
echo =========================================================================
echo.

set PYTHON_EXEC=python
if exist "%~dp0venv\Scripts\python.exe" (
    echo [环境检测] 检测到专用虚拟环境 venv，自动启用: %~dp0venv\Scripts\python.exe
    set PYTHON_EXEC="%~dp0venv\Scripts\python.exe"
) else (
    echo [环境检测] 未找到独立 venv，使用全局 Python 环境
)

echo.
echo [1/2] 正在启动后端与前端整合服务 (FastAPI + Vue3)...
echo [2/2] 服务端口: 8008
echo.
echo 提示:
echo  - 系统主界面 (前后端整合): http://127.0.0.1:8008
echo  - Swagger API 接口文档:    http://127.0.0.1:8008/docs
echo  - ReDoc API 接口文档:      http://127.0.0.1:8008/redoc
echo.
echo 按 Ctrl+C 可停止运行。
echo =========================================================================
%PYTHON_EXEC% "%~dp0backend\run_server.py"
pause
