"""Отчёты по реестру: шаблоны, формирование файлов, история и выгрузка."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.deps import AdminUser, CurrentUser, SessionDep
from app.core.logging_config import get_logger
from app.db.clickhouse import ClickHouseError
from app.schemas.listing import ReportGenerateRequest, ReportOut
from app.services import report_service

logger = get_logger(__name__)
router = APIRouter(tags=["Отчёты"], prefix="/reports")

MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@router.get("/templates", summary="Доступные шаблоны отчётов")
async def templates(_: CurrentUser) -> list[dict]:
    return report_service.templates_payload()


@router.post(
    "/generate",
    response_model=ReportOut,
    summary="Сформировать отчёт в формате Excel либо PDF",
)
async def generate(payload: ReportGenerateRequest, session: SessionDep, user: CurrentUser):
    logger.info(
        "Формирование отчёта %s (%s) пользователем %s",
        payload.template,
        payload.file_format,
        user.username,
    )
    try:
        return await report_service.generate(
            session,
            template_key=payload.template,
            file_format=payload.file_format,
            parameters=payload.parameters,
            created_by=user.username,
        )
    except report_service.ReportError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ClickHouseError as exc:
        logger.error("Данные для отчёта не получены: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Данные для отчёта не получены из ClickHouse: {exc}",
        ) from exc


@router.get("", response_model=list[ReportOut], summary="История сформированных отчётов")
async def history(session: SessionDep, _: CurrentUser, limit: int = Query(30, ge=1, le=200)):
    return await report_service.list_reports(session, limit=limit)


@router.get("/{report_id}/download", summary="Скачать файл отчёта")
async def download(report_id: int, session: SessionDep, _: CurrentUser):
    try:
        path, report = await report_service.get_report_file(session, report_id)
    except report_service.ReportError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(report.file_format, "application/octet-stream"),
        filename=report.file_name,
    )


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_200_OK,
    summary="Удалить отчёт вместе с файлом",
)
async def delete(report_id: int, session: SessionDep, _: AdminUser) -> dict:
    try:
        await report_service.delete_report(session, report_id)
    except report_service.ReportError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"detail": "Отчёт удалён"}
