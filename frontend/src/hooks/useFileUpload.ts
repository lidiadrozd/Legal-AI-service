import { useState, useCallback } from 'react';
import { documentsApi } from '@/api/documents';
import { useUIStore } from '@/store/uiStore';
import {
  ALLOWED_FILE_TYPES,
  ALLOWED_EXTENSIONS,
  MAX_FILE_SIZE_BYTES,
} from '@/types/document.types';
import type { UploadDocumentResponse } from '@/types/document.types';

interface UploadState {
  isUploading: boolean;
  progress: number;
  error: string | null;
  result: UploadDocumentResponse | null;
}

export function useFileUpload() {
  const addToast = useUIStore((s) => s.addToast);
  const [state, setState] = useState<UploadState>({
    isUploading: false,
    progress: 0,
    error: null,
    result: null,
  });

  const validateFile = (file: File): string | null => {
    if (!ALLOWED_FILE_TYPES.includes(file.type as typeof ALLOWED_FILE_TYPES[number])) {
      const ext = ALLOWED_EXTENSIONS.join(', ');
      return `Недопустимый формат файла. Разрешены: ${ext}`;
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      return 'Файл слишком большой. Максимальный размер: 20 МБ';
    }
    return null;
  };

  const upload = useCallback(
    async (file: File): Promise<UploadDocumentResponse | null> => {
      const validationError = validateFile(file);
      if (validationError) {
        setState((s) => ({ ...s, error: validationError }));
        addToast({ message: validationError, type: 'error' });
        return null;
      }

      setState({ isUploading: true, progress: 0, error: null, result: null });

      try {
        const result = await documentsApi.upload(file, (percent) => {
          setState((s) => ({ ...s, progress: percent }));
        });
        setState({ isUploading: false, progress: 100, error: null, result });
        addToast({ message: `Файл «${file.name}» загружен`, type: 'success' });
        return result;
      } catch {
        const errorMsg = 'Ошибка загрузки файла. Попробуйте ещё раз.';
        setState({ isUploading: false, progress: 0, error: errorMsg, result: null });
        addToast({ message: errorMsg, type: 'error' });
        return null;
      }
    },
    [addToast]
  );

  const reset = useCallback(() => {
    setState({ isUploading: false, progress: 0, error: null, result: null });
  }, []);

  return { ...state, upload, reset };
}

