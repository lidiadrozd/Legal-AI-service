import { useState } from 'react';
import { documentsApi } from '@/api/documents';
import { useUIStore } from '@/store/uiStore';
import {
  ALLOWED_FILE_TYPES,
  MAX_FILE_SIZE_BYTES,
  type AllowedFileType,
  type UploadDocumentResponse,
} from '@/types/document.types';

function effectiveMime(file: File): string {
  if (file.type && file.type !== 'application/octet-stream') {
    return file.type;
  }
  const n = file.name.toLowerCase();
  if (n.endsWith('.pdf')) return 'application/pdf';
  if (n.endsWith('.docx')) return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  if (n.endsWith('.txt')) return 'text/plain';
  return '';
}

interface UseFileUploadResult {
  upload: (file: File) => Promise<UploadDocumentResponse | null>;
  progress: number;
  isUploading: boolean;
  reset: () => void;
}

export function useFileUpload(): UseFileUploadResult {
  const [progress, setProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const addToast = useUIStore((s) => s.addToast);

  const reset = () => {
    setProgress(0);
    setIsUploading(false);
  };

  const upload = async (file: File): Promise<UploadDocumentResponse | null> => {
    const mime = effectiveMime(file);
    if (!ALLOWED_FILE_TYPES.includes(mime as AllowedFileType)) {
      addToast({ type: 'error', message: 'Неподдерживаемый тип файла (нужны PDF, DOCX или TXT)' });
      return null;
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      addToast({ type: 'error', message: 'Файл превышает 20 МБ' });
      return null;
    }

    try {
      setIsUploading(true);
      setProgress(0);
      const result = await documentsApi.upload(file, setProgress);
      setProgress(100);
      return result;
    } catch {
      addToast({ type: 'error', message: 'Не удалось загрузить файл' });
      return null;
    } finally {
      setIsUploading(false);
    }
  };

  return {
    upload,
    progress,
    isUploading,
    reset,
  };
}
