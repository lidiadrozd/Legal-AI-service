import { useState, useCallback } from 'react';
import { AxiosError } from 'axios';
import { documentsApi } from '@/api/documents';
import { useUIStore } from '@/store/uiStore';
import type { UploadDocumentResponse } from '@/types/document.types';
import {
  ALLOWED_EXTENSIONS,
  ALLOWED_FILE_TYPES,
  MAX_FILE_SIZE_BYTES,
} from '@/types/document.types';
import type { AllowedFileType } from '@/types/document.types';

function getExt(name: string): string {
  const i = name.lastIndexOf('.');
  return i >= 0 ? name.slice(i).toLowerCase() : '';
}

function effectiveMime(file: File): string {
  if (file.type && file.type !== 'application/octet-stream') {
    return file.type;
  }
  const ext = getExt(file.name);
  if (ext === '.pdf') return 'application/pdf';
  if (ext === '.docx') return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  if (ext === '.txt') return 'text/plain';
  return '';
}

function extractServerError(err: unknown): string {
  if (err instanceof AxiosError) {
    if (err.code === 'ECONNABORTED') return 'Истекло время ожидания ответа сервера';
    if (err.code === 'ERR_NETWORK' || err.message === 'Network Error') {
      return (
        'Сеть: запрос не дошёл до API. Если сайт открыт по HTTPS, адрес API должен быть HTTPS ' +
        '(иначе браузер блокирует загрузку). Проверьте VITE_API_BASE_URL в Vercel.'
      );
    }
    const status = err.response?.status;
    const data = err.response?.data as { detail?: unknown; error?: unknown } | undefined;
    const detail = data?.detail;
    const legacyError = data?.error;
    let detailStr = '';
    if (typeof detail === 'string') detailStr = detail;
    else if (Array.isArray(detail)) detailStr = detail.map((d) => JSON.stringify(d)).join('; ');
    else if (typeof legacyError === 'string') detailStr = legacyError;
    if (status === 401) return 'Требуется авторизация — войдите снова';
    if (status === 404) return detailStr || 'Метод не найден на сервере (обновите бэкенд)';
    if (status === 413) return 'Файл слишком большой';
    if (status === 422) return detailStr || 'Файл не прошёл валидацию';
    if (status && status >= 500) return `Ошибка сервера (${status}). ${detailStr}`.trim();
    if (detailStr) return detailStr;
    if (err.message) return err.message;
  }
  return 'Не удалось загрузить файл';
}

export function useFileUpload() {
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const addToast = useUIStore((s) => s.addToast);

  const upload = useCallback(async (file: File): Promise<UploadDocumentResponse | null> => {
    if (file.size > MAX_FILE_SIZE_BYTES) {
      addToast({ message: 'Файл слишком большой (максимум 20 МБ)', type: 'error' });
      return null;
    }

    const mime = effectiveMime(file);
    const ext = getExt(file.name);
    const mimeOk = ALLOWED_FILE_TYPES.includes(mime as AllowedFileType);
    const extOk = ALLOWED_EXTENSIONS.includes(ext);
    if (!mimeOk && !extOk) {
      addToast({
        message: `Недопустимый тип файла. Разрешены: ${ALLOWED_EXTENSIONS.join(', ')}`,
        type: 'error',
      });
      return null;
    }

    setIsUploading(true);
    setProgress(0);

    try {
      const result = await documentsApi.upload(file, (pct) => setProgress(pct));
      setProgress(100);
      return result;
    } catch (err) {
      const message = extractServerError(err);
      addToast({ message, type: 'error' });
      return null;
    } finally {
      setIsUploading(false);
    }
  }, [addToast]);

  const reset = useCallback(() => {
    setIsUploading(false);
    setProgress(0);
  }, []);

  return { upload, isUploading, progress, reset };
}
