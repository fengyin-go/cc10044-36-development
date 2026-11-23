"""上线审查接口：样本核验、上线阶段清单、上线单提交与 ETL 部署取数。

固定前缀 /api/release，与通用资源路由 /api/{module} 分开注册，
避免被动态模块路径抢先匹配。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.release_review import release_service

router = APIRouter(prefix="/api/release", tags=["上线审查"])


@router.get("/overview")
def overview() -> dict[str, Any]:
    """上线审查总览：上线单、各分支现行版本和待补样本。"""
    return release_service.overview()


@router.get("/plans")
def list_plans(branch: str | None = Query(default=None)) -> dict[str, Any]:
    """按分支列出转换步骤版本及其核验状态。"""
    items = release_service.plans(branch=branch)
    return {"items": items, "total": len(items)}


@router.get("/plans/{plan_id}/sample-template")
def sample_template(plan_id: int) -> dict[str, Any]:
    """给出该步骤的样本格式预填，仅作录入参考，不会自动成为核验记录。"""
    return release_service.sample_template(plan_id)


@router.get("/samples")
def list_samples(
    branch: str | None = Query(default=None),
    version: str | None = Query(default=None),
    step_key: str | None = Query(default=None),
) -> dict[str, Any]:
    items = release_service.list_samples(branch=branch, version=version, step_key=step_key)
    return {"items": items, "total": len(items)}


@router.post("/samples")
def ingest_sample(payload: dict[str, Any]) -> dict[str, Any]:
    """录入样本；录入时固化输入、输出和转换版本，状态为待核验。"""
    return release_service.ingest_sample(payload)


@router.post("/samples/{sample_id}/verify")
def verify_sample(sample_id: int) -> dict[str, Any]:
    """按步骤规则校验样本输出，通过后生成带输入/输出/版本快照的核验记录。"""
    result = release_service.verify_sample(sample_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("message", "样本核验失败"))
    return result


@router.post("/reviews")
def create_review(payload: dict[str, Any]) -> dict[str, Any]:
    """录入并核验一条样本，供页面一次提交完成。"""
    result = release_service.verify_and_ingest(payload)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "样本核验失败"))
    return result


@router.get("/reviews")
def list_reviews(
    branch: str | None = Query(default=None),
    version: str | None = Query(default=None),
    step_key: str | None = Query(default=None),
) -> dict[str, Any]:
    items = release_service.list_reviews(branch=branch, version=version, step_key=step_key)
    return {"items": items, "total": len(items)}


@router.get("/checklist")
def checklist(order_id: int = Query(default=1, ge=1)) -> dict[str, Any]:
    """生成上线阶段清单：每个分支下一步采用的版本和输出数据表。"""
    result = release_service.build_checklist(order_id)
    if not result.get("ok", True):
        raise HTTPException(status_code=404, detail=result.get("message", "上线单不存在"))
    return result


@router.get("/orders")
def list_orders() -> dict[str, Any]:
    items = release_service.orders()
    return {"items": items, "total": len(items)}


@router.get("/orders/{order_id}")
def order_detail(order_id: int) -> dict[str, Any]:
    result = release_service.order_detail(order_id)
    if result is None:
        raise HTTPException(status_code=404, detail="上线单不存在")
    return result


@router.post("/orders/{order_id}/submit")
def submit_order(order_id: int) -> dict[str, Any]:
    """提交上线单：固化本次上线阶段清单，只推进已核验的分支。"""
    result = release_service.submit_order(order_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("message", "上线单不存在"))
    return result


@router.post("/orders/{order_id}/deploy")
def deploy_order(order_id: int) -> dict[str, Any]:
    """ETL 部署接收上线请求：按清单为每个分支流水线选择方案版本和输出表。"""
    result = release_service.deploy_order(order_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("message", "部署失败"))
    return result


@router.post("/fetch")
def run_fetch(payload: dict[str, Any]) -> dict[str, Any]:
    """按上线阶段清单对生产表取数，并记录实际采用的版本和输出表。"""
    return release_service.run_fetch(payload)


@router.get("/fetch")
def fetch_history() -> dict[str, Any]:
    return release_service.fetch_history()


@router.get("/usage")
def usage(tables: str | None = Query(default=None)) -> dict[str, Any]:
    """按版本汇总取数记录，用于核对旧版/新版的使用边界。"""
    wanted = [item.strip() for item in tables.split(",") if item.strip()] if tables else None
    return release_service.usage(tables=wanted)
