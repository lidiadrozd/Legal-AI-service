import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.court_filing import CourtFiling, CourtFilingDocument
from app.models.user import User
from app.schemas.court_filing import CourtFilingCreate, CourtFilingOut, CourtFilingStatusUpdate

router = APIRouter(prefix="/court-filings", tags=["Court Filings"])
logger = logging.getLogger(__name__)


@router.post(
    "/submissions",
    response_model=CourtFilingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Подать документы в суд",
    responses={
        201: {"description": "Документы успешно отправлены"},
        400: {"description": "Ошибка валидации документов"},
        401: {"description": "Требуется авторизация"},
        500: {"description": "Внутренняя ошибка сервера"},
    },
)
async def create_filing(
    payload: CourtFilingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        tracking_number = f"CF-{uuid4().hex[:12].upper()}"
        filing = CourtFiling(
            user_id=current_user.id,
            case_number=payload.case_number,
            court_name=payload.court_name,
            claim_type=payload.claim_type,
            status="submitted",
            tracking_number=tracking_number,
        )
        for doc in payload.documents:
            filing.documents.append(
                CourtFilingDocument(
                    filename=doc.filename,
                    mime_type=doc.mime_type,
                    size_bytes=doc.size_bytes,
                )
            )

        db.add(filing)
        await db.commit()
        await db.refresh(filing, attribute_names=["documents"])
        logger.info(
            "Court filing created: filing_id=%s user_id=%s tracking=%s",
            filing.id,
            current_user.id,
            tracking_number,
        )
        return filing
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to create court filing for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to submit court filing") from exc


@router.get(
    "/submissions",
    response_model=list[CourtFilingOut],
    summary="Список подач текущего пользователя",
)
async def list_filings(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CourtFiling)
        .where(CourtFiling.user_id == current_user.id)
        .options(selectinload(CourtFiling.documents))
        .order_by(CourtFiling.id.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get(
    "/submissions/{filing_id}",
    response_model=CourtFilingOut,
    summary="Детали подачи документов",
    responses={404: {"description": "Подача не найдена"}},
)
async def get_filing(
    filing_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CourtFiling)
        .where(CourtFiling.id == filing_id, CourtFiling.user_id == current_user.id)
        .options(selectinload(CourtFiling.documents))
    )
    result = await db.execute(stmt)
    filing = result.scalar_one_or_none()
    if not filing:
        logger.warning("Court filing not found: filing_id=%s user_id=%s", filing_id, current_user.id)
        raise HTTPException(status_code=404, detail="Court filing not found")
    return filing


@router.patch(
    "/submissions/{filing_id}/status",
    response_model=CourtFilingOut,
    summary="Обновить статус подачи",
    responses={
        404: {"description": "Подача не найдена"},
        422: {"description": "Некорректный статус"},
    },
)
async def update_filing_status(
    filing_id: int,
    payload: CourtFilingStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CourtFiling)
        .where(CourtFiling.id == filing_id, CourtFiling.user_id == current_user.id)
        .options(selectinload(CourtFiling.documents))
    )
    filing = result.scalar_one_or_none()
    if not filing:
        raise HTTPException(status_code=404, detail="Court filing not found")

    filing.status = payload.status.value
    filing.comment = payload.comment
    db.add(filing)
    await db.commit()
    await db.refresh(filing, attribute_names=["documents"])
    logger.info(
        "Court filing status updated: filing_id=%s user_id=%s status=%s",
        filing_id,
        current_user.id,
        payload.status.value,
    )
    return filing
