from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response

from ..dependencies import get_data_service, get_ecos_service
from ..models import DataCreate, DataRecord, DataUpdate, Indicator
from ..services.data_service import DataService, validate_period
from ..services.ecos_service import EcosSyncService


router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("/summary")
def get_summary(service: DataService = Depends(get_data_service)) -> dict:
    """프롬프트 주입과 대시보드에 사용하는 전체 데이터 요약."""
    return service.summary()


@router.get("/compare")
def compare_periods(
    period_a_start: str,
    period_a_end: str,
    period_b_start: str,
    period_b_end: str,
    indicators: list[Indicator] = Query(default=list(Indicator)),
    service: DataService = Depends(get_data_service),
) -> dict:
    for value in (period_a_start, period_a_end, period_b_start, period_b_end):
        validate_period(value)
    if period_a_start > period_a_end or period_b_start > period_b_end:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="시작 월은 종료 월보다 늦을 수 없습니다.")
    return service.compare(
        period_a_start,
        period_a_end,
        period_b_start,
        period_b_end,
        indicators[:3],
    )


@router.get("/export")
def export_data(
    format: Literal["csv", "json"] = "csv",
    service: DataService = Depends(get_data_service),
) -> Response:
    if format == "json":
        content = json.dumps(
            service.list_records(include_deleted=True, limit=100_000),
            ensure_ascii=False,
            indent=2,
        )
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=econscope-data.json"},
        )
    return Response(
        content=service.export_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=econscope-data.csv"},
    )


@router.get("/sync-status")
def sync_status(service: EcosSyncService = Depends(get_ecos_service)) -> dict:
    return service.status()


@router.post("/sync")
def sync_data(
    force: bool = True,
    service: EcosSyncService = Depends(get_ecos_service),
) -> dict:
    """한국은행 ECOS의 최신 월별 데이터를 확인한다."""
    return service.sync(force=force)


@router.post("/restore-all")
def restore_all(service: DataService = Depends(get_data_service)) -> dict:
    return service.restore_all()


@router.get("", response_model=list[DataRecord])
def list_data(
    indicator: Indicator | None = None,
    start: str | None = None,
    end: str | None = None,
    include_deleted: bool = False,
    limit: int = Query(default=1_000, ge=1, le=10_000),
    service: DataService = Depends(get_data_service),
) -> list[dict]:
    if start:
        validate_period(start)
    if end:
        validate_period(end)
    return service.list_records(
        indicator=indicator,
        start=start,
        end=end,
        include_deleted=include_deleted,
        limit=limit,
    )


@router.post("", response_model=DataRecord, status_code=201)
def create_data(
    payload: DataCreate,
    service: DataService = Depends(get_data_service),
) -> dict:
    return service.create_record(payload)


@router.put("/{record_id}", response_model=DataRecord)
def update_data(
    record_id: str,
    payload: DataUpdate,
    service: DataService = Depends(get_data_service),
) -> dict:
    return service.update_record(record_id, payload)


@router.delete("/{record_id}", response_model=DataRecord)
def delete_data(
    record_id: str,
    service: DataService = Depends(get_data_service),
) -> dict:
    return service.soft_delete(record_id)


@router.post("/{record_id}/restore", response_model=DataRecord)
def restore_data(
    record_id: str,
    service: DataService = Depends(get_data_service),
) -> dict:
    return service.restore_record(record_id)

