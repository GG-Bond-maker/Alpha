from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.recommend import router as recommend_router
from backend.app.api.explain import router as explain_router
from backend.app.api.evaluation import router as eval_router
from backend.app.api.stock import router as stock_router
from backend.app.api.data_engineering import router as engineering_router

app = FastAPI(
    title="基于 LightGBM 与特征归因的主板股票智能选股与可视化推荐系统 API",
    description="包含基于 A 股主板的 LightGBM 推荐预测、专业日K线走势可视化、TreeSHAP 特征归因、评测服务及数据工程与模型生命周期管理。",
    version="2.0.0"
)

# 允许跨域请求（前端 Vue 联调）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os
from fastapi.staticfiles import StaticFiles

# 注册 API 路由
app.include_router(recommend_router, prefix="/api/v1")
app.include_router(explain_router, prefix="/api/v1")
app.include_router(eval_router, prefix="/api/v1")
app.include_router(stock_router, prefix="/api/v1")
app.include_router(engineering_router, prefix="/api/v1")

@app.get("/api/health", summary="服务健康检查")
def health():
    return {
        "status": "healthy",
        "service": "Stock Top-K Recommender & Attribution API",
        "docs_url": "/docs",
        "version": "1.0.0"
    }

# 挂载前端打包静态资源（如已构建 dist，则直接访问根路径即可打开完整 Vue 界面）
dist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "dist")
if os.path.exists(dist_dir):
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8008, reload=True)
