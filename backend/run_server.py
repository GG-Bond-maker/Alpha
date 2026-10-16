import os
import sys
import socket

# 保证在 Windows GBK 控制台下输出不会因为特殊字符报错
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 将工程根目录添加到 Python 搜索路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn


def find_available_port(start_port=8008, max_attempts=10):
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port


if __name__ == "__main__":
    port = find_available_port(8008)
    print("=================================================================")
    print(" >>> 正在启动 股票 Top-K 推荐与特征归因系统 FastAPI 后端服务...")
    print(f" >>> 系统前端主界面 (整合版): http://127.0.0.1:{port}")
    print(f" >>> 交互式 API 文档 (Swagger): http://127.0.0.1:{port}/docs")
    print(f" >>> 备用 API 文档 (ReDoc):    http://127.0.0.1:{port}/redoc")
    print("=================================================================")
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=port, reload=False)
