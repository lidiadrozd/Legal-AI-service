import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user
from app.core.config import settings
from app.models.user import User
from app.schemas.speech import TranscribeResponse
from app.services.audio_convert import transcode_to_pcm16
from app.services.salute_speech_client import is_salute_speech_configured, recognize_pcm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/speech", tags=["Speech"])

# Лимит SaluteSpeech sync API: 2 МБ, ~1 мин
MAX_AUDIO_BYTES = 2 * 1024 * 1024


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_speech(
    audio: UploadFile = File(..., description="Аудиозапись (webm, ogg, wav, mp3)"),
    current_user: User = Depends(get_current_user),
):
    """Распознавание речи через SaluteSpeech (синхронный REST API)."""
    _ = current_user

    if not is_salute_speech_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "SaluteSpeech не настроен. Добавьте SALUTE_SPEECH_CLIENT_ID и "
                "SALUTE_SPEECH_CLIENT_SECRET в .env (или используйте ключи GigaChat со scope SaluteSpeech)."
            ),
        )

    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Файл пустой")
    if len(raw) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=422,
            detail="Запись слишком длинная (максимум ~1 минуты или 2 МБ). Остановите запись раньше.",
        )

    try:
        pcm = transcode_to_pcm16(
            raw,
            sample_rate=settings.SALUTE_SPEECH_SAMPLE_RATE,
            content_type=audio.content_type,
            filename=audio.filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        text = await recognize_pcm(pcm, sample_rate=settings.SALUTE_SPEECH_SAMPLE_RATE)
    except RuntimeError as exc:
        logger.exception("SaluteSpeech transcribe failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("SaluteSpeech transcribe unexpected error")
        raise HTTPException(
            status_code=502,
            detail="Не удалось распознать речь. Попробуйте ещё раз.",
        ) from exc

    return TranscribeResponse(text=text)
