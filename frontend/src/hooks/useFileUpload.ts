import { useState, useCallback } from 'react';
import { documentsApi } from '@/api/documents';
import { useUIStore } from '@/store/uiStore';
import type { UploadDocumentResponse } from '@/types/document.types';
import { ALLOWED_FILE_TYPES, MAX_FILE_SIZE_BYTES } from '@/types/document.types';
import type { AllowedFileType } from '@/types/document.types';

export function useFileUpload() {
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const addToast = useUIStore((s) => s.addToast);

  const upload = useCallback(async (file: File): Promise<UploadDocumentResponse | null> => {
    if (file.size > MAX_FILE_SIZE_BYTES) {
      addToast({ message: 'Файл слишком большой (максимум 20 МБ)', type: 'error' });
      return null;
    }

    if (!ALLOWED_FILE_TYPES.includes(file.type as AllowedFileType)) {
      addToast({ message: 'Недопустимый тип файла. Разрешены: PDF, DOCX, TXT', type: 'error' });
      return null;
    }

    setIsUploading(true);
    setProgress(0);

    try {
      const result = await documentsApi.upload(file, (pct) => setProgress(pct));
      return result;
    } catch {
      addToast({ message: 'Не удалось загрузить файл', type: 'error' });
      return null;
    } finally {
      setIsUploading(false);
      setProgress(0);
    }
  }, [addToast]);

  const reset = useCallback(() => {
    setIsUploading(false);
    setProgress(0);
  }, []);

  return { upload, isUploading, progress, reset };
}
