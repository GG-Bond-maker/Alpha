from fastapi import APIRouter
from typing import Dict, Any
from backend.app.services.recommend_service import service_instance

router = APIRouter(prefix="/evaluation", tags=["推荐系统评估"])


@router.get("/metrics", summary="获取各模型推荐评估指标对比表 (NDCG@K, Precision@K, HitRate等)")
def get_evaluation_metrics() -> Dict[str, Any]:
    return service_instance.get_evaluation_metrics()
