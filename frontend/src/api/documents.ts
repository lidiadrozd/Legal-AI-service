import apiClient from './client';
import type { Document, UploadDocumentResponse } from '@/types/document.types';
import { capitalizeFilename } from '@/utils/capitalizeFirst';

export const documentsApi = {
  upload: async (
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<UploadDocumentResponse> => {
    const form = new FormData();
    form.append('file', file);

    const response = await apiClient.post<UploadDocumentResponse>('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (e.total && onProgress) {
          onProgress(Math.round((e.loaded * 100) / e.total));
        }
      },
    });
    return {
      ...response.data,
      filename: capitalizeFilename(response.data.filename),
    };
  },

  list: async (): Promise<Document[]> => {
    const response = await apiClient.get<Document[]>('/documents');
    return response.data.map((d) => ({ ...d, title: capitalizeFilename(d.title) }));
  },

  getById: async (id: string): Promise<Document> => {
    const response = await apiClient.get<Document>(`/documents/${id}`);
    return { ...response.data, title: capitalizeFilename(response.data.title) };
  },

  download: async (id: string, filename: string): Promise<void> => {
    const response = await apiClient.get(`/documents/${id}/download`, {
      responseType: 'blob',
    });
    const url = URL.createObjectURL(new Blob([response.data]));
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/documents/${id}`);
  },

  /** Удалить все документы пользователя. */
  clearAll: async (): Promise<{ deleted: number }> => {
    const response = await apiClient.delete<{ deleted: number }>('/documents/all');
    return response.data;
  },
};
